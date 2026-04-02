#!/usr/bin/env node
// Sorta.Fit — Setup Wizard Server
// Zero-dependency Node.js HTTP server (built-ins only)

const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync, spawn } = require('child_process');
const os = require('os');
const url = require('url');

const PORT = 3456;
const SETUP_DIR = __dirname;
const PROJECT_ROOT = path.resolve(SETUP_DIR, '..');

// Track runner child process
let runnerProcess = null;
let runnerPID = null;

// ─── Content-Type map ───────────────────────────────────────────────

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif':  'image/gif',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf':  'font/ttf',
};

// ─── Helpers ────────────────────────────────────────────────────────

function corsHeaders() {
  return {};
}

function sendJSON(res, statusCode, data) {
  const body = JSON.stringify(data, null, 2);
  res.writeHead(statusCode, {
    ...corsHeaders(),
    'Content-Type': 'application/json; charset=utf-8',
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => {
      try {
        const raw = Buffer.concat(chunks).toString('utf-8');
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(new Error('Invalid JSON body: ' + err.message));
      }
    });
    req.on('error', reject);
  });
}

function whichCommand(name) {
  try {
    const cmd = process.platform === 'win32' ? `where ${name}` : `which ${name}`;
    const result = execSync(cmd, { encoding: 'utf-8', timeout: 5000, stdio: ['pipe', 'pipe', 'pipe'] }).trim();
    // `where` on Windows may return multiple lines; take the first
    return result.split(/\r?\n/)[0].trim();
  } catch {
    return null;
  }
}

function getVersion(name, cmdPath) {
  try {
    const result = execSync(`"${cmdPath}" --version`, {
      encoding: 'utf-8',
      timeout: 5000,
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
    // Take just the first line
    return result.split(/\r?\n/)[0].trim();
  } catch {
    return 'unknown';
  }
}

function isProcessRunning(pid) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function openBrowser(url) {
  const platform = os.platform();
  try {
    if (platform === 'win32') {
      spawn('cmd', ['/c', 'start', '', url], { detached: true, stdio: 'ignore' }).unref();
    } else if (platform === 'darwin') {
      spawn('open', [url], { detached: true, stdio: 'ignore' }).unref();
    } else {
      spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref();
    }
  } catch {
    // Silently ignore — user can open browser manually
  }
}

// ─── API Handlers ───────────────────────────────────────────────────

async function handleLoadConfig(req, res) {
  const envPath = path.join(PROJECT_ROOT, '.env');
  const env = {};

  if (fs.existsSync(envPath)) {
    const lines = fs.readFileSync(envPath, 'utf-8').split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIndex = trimmed.indexOf('=');
      if (eqIndex === -1) continue;
      const key = trimmed.substring(0, eqIndex);
      let value = trimmed.substring(eqIndex + 1);
      if ((value.startsWith('"') && value.endsWith('"')) ||
          (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      env[key] = value;
    }
  }

  const adapter = env.BOARD_ADAPTER || 'jira';
  const adapterConfigPath = path.join(PROJECT_ROOT, 'adapters', `${adapter}.config.sh`);
  const statuses = [];
  const transitions = [];

  if (fs.existsSync(adapterConfigPath)) {
    const configLines = fs.readFileSync(adapterConfigPath, 'utf-8').split(/\r?\n/);
    for (const line of configLines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;

      const statusMatch = trimmed.match(/^STATUS_(\d+)=["']?(.+?)["']?$/);
      if (statusMatch) {
        statuses.push({ id: statusMatch[1], name: statusMatch[2] });
        continue;
      }

      const transMatch = trimmed.match(/^TRANSITION_TO_(\d+)=(\d+)$/);
      if (transMatch) {
        transitions.push({ statusId: transMatch[1], transitionId: transMatch[2] });
      }
    }
  }

  sendJSON(res, 200, { success: true, env, statuses, transitions });
}

async function handleCheckDependencies(req, res) {
  const deps = ['git', 'node', 'claude', 'gh'];
  const results = [];

  for (const name of deps) {
    let found = false;
    let version = '';
    let depPath = '';

    let cmdPath = whichCommand(name);

    // Special case: gh may live in a non-PATH location on Windows
    if (!cmdPath && name === 'gh' && process.platform === 'win32') {
      const ghExe = '/c/Program Files/GitHub CLI/gh.exe';
      // Also try the Windows-native path
      const ghExeWin = 'C:\\Program Files\\GitHub CLI\\gh.exe';
      try {
        if (fs.existsSync(ghExeWin) || fs.existsSync(ghExe)) {
          cmdPath = fs.existsSync(ghExeWin) ? ghExeWin : ghExe;
        }
      } catch {
        // ignore
      }
    }

    if (cmdPath) {
      found = true;
      depPath = cmdPath;
      version = getVersion(name, cmdPath);
    }

    results.push({ name, found, version, path: depPath });
  }

  // On Windows, verify git-bash.exe exists (needed for runner terminal)
  if (process.platform === 'win32') {
    const gitBashPaths = [
      'C:\\Program Files\\Git\\git-bash.exe',
      'C:\\Program Files (x86)\\Git\\git-bash.exe',
    ];
    let gitBashFound = false;
    let gitBashPath = '';
    for (const p of gitBashPaths) {
      if (fs.existsSync(p)) {
        gitBashFound = true;
        gitBashPath = p;
        break;
      }
    }
    results.push({
      name: 'git-bash',
      found: gitBashFound,
      version: gitBashFound ? 'found' : 'not found',
      path: gitBashPath,
    });
  }

  sendJSON(res, 200, { dependencies: results });
}

async function handleTestConnection(req, res) {
  const body = await readBody(req);
  const { adapter, domain, email, token, projectKey } = body;

  if (!adapter || !domain || !token) {
    return sendJSON(res, 400, { success: false, message: 'Missing required fields: adapter, domain, token' });
  }

  if (adapter === 'jira') {
    if (!email) {
      return sendJSON(res, 400, { success: false, message: 'Jira adapter requires email field' });
    }

    try {
      const auth = Buffer.from(`${email}:${token}`).toString('base64');
      const jiraUrl = `https://${domain}/rest/api/3/myself`;

      // Use Node built-in https
      const result = await new Promise((resolve, reject) => {
        const https = require('https');
        const parsed = new URL(jiraUrl);

        const reqOpts = {
          hostname: parsed.hostname,
          port: 443,
          path: parsed.pathname,
          method: 'GET',
          headers: {
            'Authorization': `Basic ${auth}`,
            'Accept': 'application/json',
          },
        };

        const request = https.request(reqOpts, (response) => {
          const chunks = [];
          response.on('data', (chunk) => chunks.push(chunk));
          response.on('end', () => {
            const raw = Buffer.concat(chunks).toString('utf-8');
            try {
              resolve({ statusCode: response.statusCode, data: JSON.parse(raw) });
            } catch {
              resolve({ statusCode: response.statusCode, data: raw });
            }
          });
        });

        request.on('error', reject);
        request.setTimeout(15000, () => {
          request.destroy();
          reject(new Error('Request timed out'));
        });
        request.end();
      });

      if (result.statusCode === 200 && result.data && result.data.displayName) {
        sendJSON(res, 200, {
          success: true,
          message: `Connected as ${result.data.displayName}`,
          user: {
            displayName: result.data.displayName,
            emailAddress: result.data.emailAddress,
            accountId: result.data.accountId,
          },
        });
      } else {
        const msg = result.data && result.data.message
          ? result.data.message
          : `HTTP ${result.statusCode} — check credentials and domain`;
        sendJSON(res, 200, { success: false, message: msg });
      }
    } catch (err) {
      sendJSON(res, 200, { success: false, message: `Connection failed: ${err.message}` });
    }
  } else {
    sendJSON(res, 400, { success: false, message: `Adapter "${adapter}" is not yet supported in the setup wizard` });
  }
}

async function handleDiscoverBoard(req, res) {
  const body = await readBody(req);
  const { adapter, domain, email, token, projectKey } = body;

  if (!adapter || !domain || !token || !projectKey) {
    return sendJSON(res, 400, { success: false, message: 'Missing required fields' });
  }

  if (adapter === 'jira') {
    if (!email) {
      return sendJSON(res, 400, { success: false, message: 'Jira adapter requires email field' });
    }

    const auth = Buffer.from(`${email}:${token}`).toString('base64');
    const https = require('https');

    // Helper for HTTPS GET requests
    function jiraGet(urlPath) {
      return new Promise((resolve, reject) => {
        const reqOpts = {
          hostname: domain,
          port: 443,
          path: urlPath,
          method: 'GET',
          headers: {
            'Authorization': `Basic ${auth}`,
            'Accept': 'application/json',
          },
        };

        const request = https.request(reqOpts, (response) => {
          const chunks = [];
          response.on('data', (chunk) => chunks.push(chunk));
          response.on('end', () => {
            const raw = Buffer.concat(chunks).toString('utf-8');
            try {
              resolve({ statusCode: response.statusCode, data: JSON.parse(raw) });
            } catch {
              resolve({ statusCode: response.statusCode, data: raw });
            }
          });
        });

        request.on('error', reject);
        request.setTimeout(15000, () => {
          request.destroy();
          reject(new Error('Request timed out'));
        });
        request.end();
      });
    }

    // Helper for HTTPS POST requests (JQL search)
    function jiraPost(urlPath, body) {
      return new Promise((resolve, reject) => {
        const payload = JSON.stringify(body);
        const reqOpts = {
          hostname: domain,
          port: 443,
          path: urlPath,
          method: 'POST',
          headers: {
            'Authorization': `Basic ${auth}`,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload),
          },
        };

        const request = https.request(reqOpts, (response) => {
          const chunks = [];
          response.on('data', (chunk) => chunks.push(chunk));
          response.on('end', () => {
            const raw = Buffer.concat(chunks).toString('utf-8');
            try {
              resolve({ statusCode: response.statusCode, data: JSON.parse(raw) });
            } catch {
              resolve({ statusCode: response.statusCode, data: raw });
            }
          });
        });

        request.on('error', reject);
        request.setTimeout(15000, () => {
          request.destroy();
          reject(new Error('Request timed out'));
        });
        request.end(payload);
      });
    }

    try {
      // 1. Fetch project statuses
      const statusResult = await jiraGet(`/rest/api/3/project/${encodeURIComponent(projectKey)}/statuses`);

      if (statusResult.statusCode !== 200) {
        const msg = statusResult.data && statusResult.data.errorMessages
          ? statusResult.data.errorMessages.join(', ')
          : `HTTP ${statusResult.statusCode}`;
        return sendJSON(res, 200, { success: false, message: `Failed to fetch statuses: ${msg}` });
      }

      // Statuses come grouped by issue type; deduplicate
      const statusMap = new Map();
      const statusData = Array.isArray(statusResult.data) ? statusResult.data : [];
      for (const issueType of statusData) {
        if (issueType.statuses) {
          for (const s of issueType.statuses) {
            statusMap.set(s.id, { id: s.id, name: s.name });
          }
        }
      }
      const statuses = Array.from(statusMap.values());

      // 2. Fetch transitions from issues across multiple statuses
      const transitionMap = new Map();
      for (const status of statuses.slice(0, 10)) {
        try {
          const searchResult = await jiraPost('/rest/api/3/search/jql', {
            jql: `project=${projectKey} AND status=${status.id} ORDER BY rank ASC`,
            maxResults: 1,
          });
          if (searchResult.statusCode === 200 && searchResult.data.issues && searchResult.data.issues.length > 0) {
            const issueId = searchResult.data.issues[0].id;
            // Fetch issue to get key (search/jql only returns id)
            const issueResult = await jiraGet(`/rest/api/3/issue/${issueId}`);
            const issueKey = issueResult.statusCode === 200 ? issueResult.data.key : issueId;
            const transResult = await jiraGet(`/rest/api/3/issue/${issueKey}/transitions`);
            if (transResult.statusCode === 200 && transResult.data.transitions) {
              for (const t of transResult.data.transitions) {
                const toId = t.to ? t.to.id : null;
                if (toId && !transitionMap.has(toId)) {
                  transitionMap.set(toId, {
                    id: t.id,
                    name: t.name,
                    toName: t.to ? t.to.name : 'unknown',
                    toId: toId,
                  });
                }
              }
            }
          }
        } catch {
          // Continue to next status
        }
      }
      const transitions = Array.from(transitionMap.values());

      sendJSON(res, 200, { success: true, statuses, transitions });
    } catch (err) {
      sendJSON(res, 200, { success: false, message: `Discovery failed: ${err.message}` });
    }
  } else {
    sendJSON(res, 400, { success: false, message: `Adapter "${adapter}" is not yet supported for discovery` });
  }
}

async function handleSaveConfig(req, res) {
  const body = await readBody(req);
  const { env, adapterConfig, adapter } = body;

  if (!env || !adapter) {
    return sendJSON(res, 400, { success: false, message: 'Missing required fields: env, adapter' });
  }

  // Validate adapter name to prevent path traversal
  if (!/^[a-z][a-z0-9-]*$/.test(adapter)) {
    return sendJSON(res, 400, { success: false, message: 'Invalid adapter name' });
  }

  try {
    // 1. Write .env file to project root with human-readable comments
    const e = env;
    const q = (v) => /[\s#=]/.test(String(v)) ? `"${v}"` : v;
    const envContent = `# Sorta.Fit -- Environment Configuration
# Generated by setup wizard on ${new Date().toISOString().split('T')[0]}
# Do NOT commit .env to version control.

# =============================================================================
# Board Connection
# =============================================================================

BOARD_ADAPTER=${q(e.BOARD_ADAPTER || '')}
BOARD_DOMAIN=${q(e.BOARD_DOMAIN || '')}
BOARD_API_TOKEN=${q(e.BOARD_API_TOKEN || '')}
BOARD_PROJECT_KEY=${q(e.BOARD_PROJECT_KEY || '')}
BOARD_EMAIL=${q(e.BOARD_EMAIL || '')}

# =============================================================================
# Target Repository
# =============================================================================

# Absolute path to the repository sorta.fit operates on
${e.TARGET_REPO ? 'TARGET_REPO=' + q(e.TARGET_REPO) : '# TARGET_REPO='}

# =============================================================================
# Git
# =============================================================================

GIT_BASE_BRANCH=${q(e.GIT_BASE_BRANCH || 'main')}

# =============================================================================
# Runner Behavior
# =============================================================================

# Seconds between polling cycles
POLL_INTERVAL=${e.POLL_INTERVAL || '3600'}

# Maximum cards per cycle for each runner
MAX_CARDS_REFINE=${e.MAX_CARDS_REFINE || '5'}
MAX_CARDS_CODE=${e.MAX_CARDS_CODE || '2'}
MAX_CARDS_REVIEW=${e.MAX_CARDS_REVIEW || '10'}
MAX_CARDS_TRIAGE=${e.MAX_CARDS_TRIAGE || '5'}
MAX_CARDS_BOUNCE=${e.MAX_CARDS_BOUNCE || '10'}

# Comma-separated list of runners to run
RUNNERS_ENABLED=${e.RUNNERS_ENABLED || 'refine,code'}

# =============================================================================
# Recipe Lane Routing (status IDs from your board)
# =============================================================================

RUNNER_REFINE_FROM=${e.RUNNER_REFINE_FROM || ''}
RUNNER_REFINE_TO=${e.RUNNER_REFINE_TO || ''}

RUNNER_CODE_FROM=${e.RUNNER_CODE_FROM || ''}
RUNNER_CODE_TO=${e.RUNNER_CODE_TO || ''}

RUNNER_REVIEW_FROM=${e.RUNNER_REVIEW_FROM || ''}
RUNNER_REVIEW_TO=${e.RUNNER_REVIEW_TO || ''}

RUNNER_TRIAGE_FROM=${e.RUNNER_TRIAGE_FROM || ''}
RUNNER_TRIAGE_TO=${e.RUNNER_TRIAGE_TO || ''}

RUNNER_BOUNCE_FROM=${e.RUNNER_BOUNCE_FROM || ''}
RUNNER_BOUNCE_TO=${e.RUNNER_BOUNCE_TO || ''}

MAX_BOUNCES=${e.MAX_BOUNCES || '3'}
`;

    const envPath = path.join(PROJECT_ROOT, '.env');
    fs.writeFileSync(envPath, envContent, 'utf-8');

    // 2. Write adapter config if provided
    if (adapterConfig && Object.keys(adapterConfig).length > 0) {
      // Separate statuses and transitions for organized output
      const statusEntries = [];
      const transEntries = [];
      for (const [key, value] of Object.entries(adapterConfig)) {
        const needsQuotes = /[\s#=]/.test(String(value));
        const formatted = `${key}=${needsQuotes ? '"' + value + '"' : value}`;
        if (key.startsWith('STATUS_')) statusEntries.push(formatted);
        else if (key.startsWith('TRANSITION_TO_')) transEntries.push(formatted);
        else statusEntries.push(formatted);
      }

      const configLines = [
        '#!/usr/bin/env bash',
        `# ${adapter} adapter configuration`,
        `# Generated by setup wizard on ${new Date().toISOString().split('T')[0]}`,
        '',
        '# Status ID -> display name',
        ...statusEntries,
        '',
        '# How to transition a card TO each status (transition IDs)',
        ...transEntries,
        '',
      ];

      const adapterConfigPath = path.join(PROJECT_ROOT, 'adapters', `${adapter}.config.sh`);
      fs.writeFileSync(adapterConfigPath, configLines.join('\n'), 'utf-8');
    }

    sendJSON(res, 200, { success: true, message: 'Configuration saved' });
  } catch (err) {
    sendJSON(res, 500, { success: false, message: `Failed to save config: ${err.message}` });
  }
}

async function handleStartRunner(req, res) {
  // Check if already running
  if (runnerPID && isProcessRunning(runnerPID)) {
    return sendJSON(res, 200, { success: true, pid: runnerPID, message: 'Runner is already active' });
  }

  const body = await readBody(req);

  try {
    let runnerScript = path.join(PROJECT_ROOT, 'core', 'loop.sh');
    let cwd = PROJECT_ROOT;

    // Convert Windows paths to Git Bash-style (C:\foo → /c/foo)
    if (process.platform === 'win32') {
      runnerScript = runnerScript.replace(/\\/g, '/').replace(/^([A-Za-z]):/, (_, d) => '/' + d.toLowerCase());
      cwd = cwd.replace(/\\/g, '/').replace(/^([A-Za-z]):/, (_, d) => '/' + d.toLowerCase());
    }

    if (!fs.existsSync(path.join(PROJECT_ROOT, 'core', 'loop.sh'))) {
      return sendJSON(res, 500, { success: false, message: 'core/loop.sh not found' });
    }

    // Write runner output to a log file so we can track it
    const logPath = path.join(PROJECT_ROOT, 'runner.log');
    const logFd = fs.openSync(logPath, 'a');

    const background = body && body.background === true;

    if (background) {
      // Background mode: no visible window, output to log file
      runnerProcess = spawn('bash', [runnerScript], {
        cwd: cwd,
        stdio: ['ignore', logFd, logFd],
        env: { ...process.env },
        windowsHide: true,
      });
    } else if (process.platform === 'win32') {
      // Visible window on Windows: find git-bash and open a mintty terminal
      const gitBashPaths = [
        'C:\\Program Files\\Git\\git-bash.exe',
        'C:\\Program Files (x86)\\Git\\git-bash.exe',
      ];
      let gitBash = null;
      for (const p of gitBashPaths) {
        if (fs.existsSync(p)) { gitBash = p; break; }
      }
      if (gitBash) {
        runnerProcess = spawn(gitBash, ['--cd=' + PROJECT_ROOT, '-c', 'bash core/loop.sh; read -p "Runner exited. Press Enter to close."'], {
          stdio: 'ignore',
          env: { ...process.env },
        });
      } else {
        // Fallback: run in background if git-bash not found
        runnerProcess = spawn('bash', [runnerScript], {
          cwd: cwd,
          stdio: ['ignore', logFd, logFd],
          env: { ...process.env },
          windowsHide: true,
        });
      }
    } else {
      // Visible on macOS/Linux: inherit stdio
      runnerProcess = spawn('bash', [runnerScript], {
        cwd: cwd,
        stdio: ['ignore', logFd, logFd],
        env: { ...process.env },
      });
    }

    runnerPID = runnerProcess.pid;

    // Don't crash the server if the runner exits
    runnerProcess.on('error', () => {});
    runnerProcess.on('exit', () => {
      runnerProcess = null;
      runnerPID = null;
    });

    sendJSON(res, 200, { success: true, pid: runnerPID });
  } catch (err) {
    sendJSON(res, 500, { success: false, message: `Failed to start runner: ${err.message}` });
  }
}

async function handleStopRunner(req, res) {
  if (!runnerPID || !isProcessRunning(runnerPID)) {
    runnerProcess = null;
    runnerPID = null;
    return sendJSON(res, 200, { success: true, message: 'Runner is not active' });
  }

  try {
    process.kill(runnerPID);
    runnerProcess = null;
    runnerPID = null;
    sendJSON(res, 200, { success: true, message: 'Runner stopped' });
  } catch (err) {
    sendJSON(res, 500, { success: false, message: `Failed to stop runner: ${err.message}` });
  }
}

async function handleRunnerStatus(req, res) {
  const running = isProcessRunning(runnerPID);

  // Clear stale PID
  if (!running) {
    runnerProcess = null;
    runnerPID = null;
  }

  sendJSON(res, 200, { running, pid: runnerPID });
}

async function handleLogs(req, res) {
  const logPath = path.join(PROJECT_ROOT, 'runner.log');

  if (!fs.existsSync(logPath)) {
    return sendJSON(res, 200, { success: true, logs: '', empty: true });
  }

  try {
    const content = fs.readFileSync(logPath, 'utf8');
    const lines = content.split('\n');
    const tail = lines.slice(-200).join('\n');
    const stripped = tail.replace(/\x1b\[[0-9;]*m/g, '');
    sendJSON(res, 200, { success: true, logs: stripped, empty: false });
  } catch (err) {
    sendJSON(res, 500, { success: false, message: `Failed to read logs: ${err.message}` });
  }
}

// ─── Route table ────────────────────────────────────────────────────

const API_ROUTES = {
  '/api/load-config':        handleLoadConfig,
  '/api/check-dependencies': handleCheckDependencies,
  '/api/test-connection':    handleTestConnection,
  '/api/discover-board':     handleDiscoverBoard,
  '/api/save-config':        handleSaveConfig,
  '/api/start-runner':       handleStartRunner,
  '/api/stop-runner':        handleStopRunner,
  '/api/runner-status':      handleRunnerStatus,
  '/api/logs':               handleLogs,
};

// ─── Static file server ─────────────────────────────────────────────

function serveStaticFile(req, res, filePath) {
  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      sendJSON(res, 404, { error: 'Not found' });
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    res.writeHead(200, {
      ...corsHeaders(),
      'Content-Type': contentType,
      'Content-Length': stats.size,
    });

    const stream = fs.createReadStream(filePath);
    stream.pipe(res);
    stream.on('error', () => {
      res.writeHead(500);
      res.end('Internal server error');
    });
  });
}

// ─── Server ─────────────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  const parsed = url.parse(req.url, true);
  const pathname = parsed.pathname;

  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, corsHeaders());
    res.end();
    return;
  }

  // API routes (POST only)
  if (pathname.startsWith('/api/')) {
    if (req.method !== 'POST') {
      return sendJSON(res, 405, { error: 'Method not allowed — use POST' });
    }

    const handler = API_ROUTES[pathname];
    if (!handler) {
      return sendJSON(res, 404, { error: `Unknown API endpoint: ${pathname}` });
    }

    try {
      await handler(req, res);
    } catch (err) {
      console.error(`Error in ${pathname}:`, err);
      sendJSON(res, 500, { error: err.message });
    }
    return;
  }

  // Static files (GET only)
  if (req.method !== 'GET') {
    return sendJSON(res, 405, { error: 'Method not allowed' });
  }

  // Map / to /index.html
  let filePath;
  if (pathname === '/' || pathname === '') {
    filePath = path.join(SETUP_DIR, 'index.html');
  } else {
    // Prevent directory traversal
    const safePath = path.normalize(pathname).replace(/^(\.\.[/\\])+/, '');
    filePath = path.join(SETUP_DIR, safePath);
  }

  // Ensure resolved path is within the setup directory
  const resolvedPath = path.resolve(filePath);
  if (!resolvedPath.startsWith(path.resolve(SETUP_DIR))) {
    return sendJSON(res, 403, { error: 'Forbidden' });
  }

  serveStaticFile(req, res, resolvedPath);
});

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`\nERROR: Port ${PORT} is already in use.`);
    console.error('Another instance of the setup wizard may still be running.');
    console.error('');
    if (process.platform === 'win32') {
      console.error('To fix this, run:');
      console.error(`  netstat -ano | findstr :${PORT}`);
      console.error('  taskkill /PID <pid> /F');
    } else {
      console.error(`To fix this, run: lsof -ti:${PORT} | xargs kill`);
    }
    console.error('');
    console.error('Then try again.');
    // Keep the window open on Windows so user can read the message
    if (process.platform === 'win32') {
      console.error('Press any key to exit...');
      process.stdin.setRawMode && process.stdin.setRawMode(true);
      process.stdin.resume();
      process.stdin.once('data', () => process.exit(1));
    } else {
      process.exit(1);
    }
  } else {
    console.error('Server error:', err.message);
    process.exit(1);
  }
});

server.listen(PORT, '127.0.0.1', () => {
  const url = `http://localhost:${PORT}`;
  console.log(`Sorta.Fit setup wizard running at ${url}`);
  console.log('Press Ctrl+C to stop.\n');
  openBrowser(url);
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\nShutting down...');
  server.close();
  if (runnerPID && isProcessRunning(runnerPID)) {
    try {
      process.kill(runnerPID);
    } catch {
      // ignore
    }
  }
  process.exit(0);
});

process.on('SIGTERM', () => {
  server.close();
  process.exit(0);
});
