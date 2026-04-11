"""Sorta.Fit setup wizard HTTP server — port of setup/server.js

Zero-dependency Python HTTP server (stdlib only) that serves the setup wizard
SPA and provides JSON API endpoints for config management, board connection
testing, and board discovery.
"""
import http.server
import json
import os
import platform
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# ── MIME types ──────────────────────────────────────────────────────────

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}


# ── Helpers ─────────────────────────────────────────────────────────────

def _which(name: str) -> str | None:
    """Find an executable on PATH (like `which`/`where`)."""
    return shutil.which(name)


def _get_version(cmd_path: str) -> str:
    """Get --version output from a command."""
    try:
        result = subprocess.run(
            [cmd_path, "--version"],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        return result.stdout.strip().splitlines()[0] if result.stdout else "unknown"
    except Exception:
        return "unknown"


def _https_request(
    method: str,
    hostname: str,
    path: str,
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: int = 15,
) -> tuple[int, dict | str]:
    """Make an HTTPS request and return (status_code, parsed_json_or_raw_text)."""
    url = f"https://{hostname}{path}"
    req = Request(url, data=body, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    ctx = ssl.create_default_context()
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except (json.JSONDecodeError, Exception):
            return e.code, raw
    except URLError as e:
        raise ConnectionError(f"Connection failed: {e.reason}")
    except Exception as e:
        raise ConnectionError(f"Request failed: {e}")


def _open_browser(url: str) -> None:
    """Open a URL in the default browser."""
    try:
        plat = platform.system()
        if plat == "Windows":
            subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif plat == "Darwin":
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass  # User can open manually


def _quote_env_value(v: str) -> str:
    """Quote a value if it contains whitespace, #, or =."""
    if re.search(r"[\s#=]", str(v)):
        return f'"{v}"'
    return str(v)


# ── .env parsing (standalone — avoids circular import risk) ─────────────

def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Matches bash loader behavior."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        elif len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1]
        env[key] = value
    return env


def _parse_adapter_config(config_path: Path) -> tuple[list[dict], list[dict]]:
    """Parse adapter .config.sh for STATUS_* and TRANSITION_TO_* entries."""
    statuses: list[dict] = []
    transitions: list[dict] = []
    if not config_path.exists():
        return statuses, transitions
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^STATUS_([^=]+)=["\']?(.+?)["\']?$', line)
        if m:
            statuses.append({"id": m.group(1), "name": m.group(2)})
            continue
        m = re.match(r"^TRANSITION_TO_([^=]+)=(.+)$", line)
        if m:
            transitions.append({"statusId": m.group(1), "transitionId": m.group(2)})
    return statuses, transitions


# ── Runner process management ───────────────────────────────────────────

_runner_process: subprocess.Popen | None = None
_runner_pid: int | None = None


def _is_process_running(pid: int | None) -> bool:
    """Check if a process with the given PID is still running."""
    if pid is None:
        return False
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, encoding="utf-8",
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


# ── API Handlers ────────────────────────────────────────────────────────

def _handle_load_config(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """GET /api/load-config — read .env and adapter config."""
    env_path = sorta_root / ".env"
    env = _parse_env_file(env_path)

    adapter = env.get("BOARD_ADAPTER", "jira")
    config_path = sorta_root / "adapters" / f"{adapter}.config.sh"
    statuses, transitions = _parse_adapter_config(config_path)

    return 200, {"success": True, "env": env, "statuses": statuses, "transitions": transitions}


def _handle_check_dependencies(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/check-dependencies — check which CLI tools are installed."""
    deps_to_check = ["git", "node", "claude", "gh"]
    results = []

    for name in deps_to_check:
        cmd_path = _which(name)

        # Special case: gh on Windows may not be on PATH
        if not cmd_path and name == "gh" and platform.system() == "Windows":
            for gh_path in [
                r"C:\Program Files\GitHub CLI\gh.exe",
                r"C:\Program Files (x86)\GitHub CLI\gh.exe",
            ]:
                if Path(gh_path).exists():
                    cmd_path = gh_path
                    break

        if cmd_path:
            results.append({
                "name": name,
                "found": True,
                "version": _get_version(cmd_path),
                "path": cmd_path,
            })
        else:
            results.append({
                "name": name,
                "found": False,
                "version": "",
                "path": "",
            })

    # Windows: check for git-bash.exe (needed for runner terminal)
    if platform.system() == "Windows":
        git_bash_found = False
        git_bash_path = ""
        for p in [
            r"C:\Program Files\Git\git-bash.exe",
            r"C:\Program Files (x86)\Git\git-bash.exe",
        ]:
            if Path(p).exists():
                git_bash_found = True
                git_bash_path = p
                break
        results.append({
            "name": "git-bash",
            "found": git_bash_found,
            "version": "found" if git_bash_found else "not found",
            "path": git_bash_path,
        })

    return 200, {"dependencies": results}


def _handle_test_connection(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/test-connection — verify board credentials."""
    adapter = body.get("adapter", "")
    domain = body.get("domain", "")
    email = body.get("email", "")
    token = body.get("token", "")
    project_key = body.get("projectKey", "")

    if not adapter or not domain or (not token and adapter != "github-issues"):
        return 400, {"success": False, "message": "Missing required fields: adapter, domain, token"}

    if adapter == "jira":
        if not email:
            return 400, {"success": False, "message": "Jira adapter requires email field"}
        try:
            import base64
            auth = base64.b64encode(f"{email}:{token}".encode()).decode()
            status, data = _https_request(
                "GET", domain, "/rest/api/3/myself",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Accept": "application/json",
                },
            )
            if status == 200 and isinstance(data, dict) and data.get("displayName"):
                return 200, {
                    "success": True,
                    "message": f"Connected as {data['displayName']}",
                    "user": {
                        "displayName": data.get("displayName", ""),
                        "emailAddress": data.get("emailAddress", ""),
                        "accountId": data.get("accountId", ""),
                    },
                }
            else:
                msg = data.get("message", "") if isinstance(data, dict) else ""
                if not msg:
                    msg = f"HTTP {status} — check credentials and domain"
                return 200, {"success": False, "message": msg}
        except Exception as e:
            return 200, {"success": False, "message": f"Connection failed: {e}"}

    elif adapter == "linear":
        try:
            linear_host = domain or "api.linear.app"
            payload = json.dumps({"query": "{ viewer { id name email } }"}).encode()
            status, data = _https_request(
                "POST", linear_host, "/graphql",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                body=payload,
            )
            if (
                status == 200
                and isinstance(data, dict)
                and data.get("data", {}).get("viewer", {}).get("name")
            ):
                viewer = data["data"]["viewer"]
                return 200, {
                    "success": True,
                    "message": f"Connected as {viewer['name']} ({viewer.get('email', '')})",
                    "user": {
                        "displayName": viewer["name"],
                        "emailAddress": viewer.get("email", ""),
                    },
                }
            else:
                errors = data.get("errors", []) if isinstance(data, dict) else []
                msg = errors[0]["message"] if errors else f"HTTP {status} — check API token"
                return 200, {"success": False, "message": msg}
        except Exception as e:
            return 200, {"success": False, "message": f"Connection failed: {e}"}

    elif adapter == "github-issues":
        try:
            repo_path = project_key or ""
            is_ghe = domain and domain != "github.com"
            gh_host = domain if is_ghe else "api.github.com"
            gh_prefix = "/api/v3" if is_ghe else ""
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": "SortaFit-Setup",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if token:
                headers["Authorization"] = f"token {token}"

            status, data = _https_request(
                "GET", gh_host, f"{gh_prefix}/repos/{repo_path}",
                headers=headers,
            )
            if status == 200 and isinstance(data, dict) and data.get("full_name"):
                return 200, {
                    "success": True,
                    "message": f"Connected to {data['full_name']} ({data.get('open_issues_count', 0)} open issues)",
                }
            else:
                msg = data.get("message", "") if isinstance(data, dict) else ""
                if not msg:
                    msg = f"HTTP {status} — check token and project key (owner/repo)"
                return 200, {"success": False, "message": msg}
        except Exception as e:
            return 200, {"success": False, "message": f"Connection failed: {e}"}

    else:
        return 400, {"success": False, "message": f'Adapter "{adapter}" is not yet supported in the setup wizard'}


def _handle_discover_board(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/discover-board — fetch statuses and transitions from the board."""
    adapter = body.get("adapter", "")
    domain = body.get("domain", "")
    email = body.get("email", "")
    token = body.get("token", "")
    project_key = body.get("projectKey", "")

    if not adapter or not domain or not project_key or (not token and adapter != "github-issues"):
        return 400, {"success": False, "message": "Missing required fields"}

    if adapter == "jira":
        if not email:
            return 400, {"success": False, "message": "Jira adapter requires email field"}

        import base64
        auth = base64.b64encode(f"{email}:{token}".encode()).decode()
        jira_headers = {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        }

        try:
            # 1. Fetch project statuses
            from urllib.parse import quote
            status_code, status_data = _https_request(
                "GET", domain,
                f"/rest/api/3/project/{quote(project_key, safe='')}/statuses",
                headers=jira_headers,
            )

            if status_code != 200:
                if isinstance(status_data, dict) and status_data.get("errorMessages"):
                    msg = ", ".join(status_data["errorMessages"])
                else:
                    msg = f"HTTP {status_code}"
                return 200, {"success": False, "message": f"Failed to fetch statuses: {msg}"}

            # Statuses come grouped by issue type; deduplicate
            status_map: dict[str, dict] = {}
            if isinstance(status_data, list):
                for issue_type in status_data:
                    for s in issue_type.get("statuses", []):
                        status_map[s["id"]] = {"id": s["id"], "name": s["name"]}
            statuses = list(status_map.values())

            # 2. Fetch transitions by finding issues in each status
            transition_map: dict[str, dict] = {}
            for status_entry in statuses[:10]:
                try:
                    search_payload = json.dumps({
                        "jql": f"project={project_key} AND status={status_entry['id']} ORDER BY rank ASC",
                        "maxResults": 1,
                    }).encode()
                    s_code, s_data = _https_request(
                        "POST", domain, "/rest/api/3/search/jql",
                        headers={
                            **jira_headers,
                            "Content-Type": "application/json",
                        },
                        body=search_payload,
                    )
                    if (
                        s_code == 200
                        and isinstance(s_data, dict)
                        and s_data.get("issues")
                        and len(s_data["issues"]) > 0
                    ):
                        issue_id = s_data["issues"][0]["id"]
                        # Get issue key
                        i_code, i_data = _https_request(
                            "GET", domain, f"/rest/api/3/issue/{issue_id}",
                            headers=jira_headers,
                        )
                        issue_key = i_data.get("key", issue_id) if i_code == 200 and isinstance(i_data, dict) else issue_id
                        # Get transitions
                        t_code, t_data = _https_request(
                            "GET", domain, f"/rest/api/3/issue/{issue_key}/transitions",
                            headers=jira_headers,
                        )
                        if t_code == 200 and isinstance(t_data, dict):
                            for t in t_data.get("transitions", []):
                                to_id = t.get("to", {}).get("id") if t.get("to") else None
                                if to_id and to_id not in transition_map:
                                    transition_map[to_id] = {
                                        "id": t["id"],
                                        "name": t["name"],
                                        "toName": t.get("to", {}).get("name", "unknown"),
                                        "toId": to_id,
                                    }
                except Exception:
                    continue  # Next status

            transitions = list(transition_map.values())
            return 200, {"success": True, "statuses": statuses, "transitions": transitions}

        except Exception as e:
            return 200, {"success": False, "message": f"Discovery failed: {e}"}

    elif adapter == "linear":
        linear_host = domain or "api.linear.app"
        try:
            team_query = (
                "query($teamKey: String!) { teams(filter: { key: { eq: $teamKey } }) "
                "{ nodes { id states { nodes { id name type } } } } }"
            )
            payload = json.dumps({
                "query": team_query,
                "variables": {"teamKey": project_key},
            }).encode()
            status_code, data = _https_request(
                "POST", linear_host, "/graphql",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                body=payload,
            )
            if status_code != 200 or not isinstance(data, dict) or not data.get("data"):
                errors = data.get("errors", []) if isinstance(data, dict) else []
                msg = errors[0]["message"] if errors else f"HTTP {status_code}"
                return 200, {"success": False, "message": f"Discovery failed: {msg}"}

            teams = data.get("data", {}).get("teams", {}).get("nodes", [])
            if not teams:
                return 200, {"success": False, "message": f'Team "{project_key}" not found. Check BOARD_PROJECT_KEY.'}

            states = teams[0].get("states", {}).get("nodes", [])
            statuses = [{"id": s["id"], "name": f"{s['name']} ({s['type']})"} for s in states]
            # Linear: every state is a valid transition target
            transitions = [
                {"id": s["id"], "name": s["name"], "toName": s["name"], "toId": s["id"]}
                for s in states
            ]
            return 200, {"success": True, "statuses": statuses, "transitions": transitions}
        except Exception as e:
            return 200, {"success": False, "message": f"Discovery failed: {e}"}

    elif adapter == "github-issues":
        is_ghe = domain and domain != "github.com"
        gh_host = domain if is_ghe else "api.github.com"
        gh_prefix = "/api/v3" if is_ghe else ""
        gh_headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "SortaFit-Setup",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            gh_headers["Authorization"] = f"token {token}"

        try:
            status_code, data = _https_request(
                "GET", gh_host,
                f"{gh_prefix}/repos/{project_key}/labels?per_page=100",
                headers=gh_headers,
            )
            if status_code != 200:
                msg = data.get("message", "") if isinstance(data, dict) else ""
                if not msg:
                    msg = f"HTTP {status_code}"
                return 200, {"success": False, "message": f"Discovery failed: {msg}"}

            labels = data if isinstance(data, list) else []
            status_labels = [l for l in labels if l.get("name", "").startswith("status:")]

            if not status_labels:
                return 200, {
                    "success": False,
                    "message": (
                        'No "status:" labels found. Create labels with a "status:" prefix '
                        "(e.g., status:todo, status:refined, status:in-progress, status:done) "
                        "and run discovery again."
                    ),
                }

            statuses = [
                {"id": l["name"], "name": l.get("description") or l["name"].replace("status:", "")}
                for l in status_labels
            ]
            transitions = [
                {
                    "id": l["name"],
                    "name": l["name"],
                    "toName": l.get("description") or l["name"].replace("status:", ""),
                    "toId": l["name"],
                }
                for l in status_labels
            ]
            return 200, {"success": True, "statuses": statuses, "transitions": transitions}
        except Exception as e:
            return 200, {"success": False, "message": f"Discovery failed: {e}"}

    else:
        return 400, {"success": False, "message": f'Adapter "{adapter}" is not yet supported for discovery'}


def _handle_save_config(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/save-config — write .env and adapter config files."""
    env = body.get("env", {})
    adapter_config = body.get("adapterConfig", {})
    adapter = body.get("adapter", "")

    if not env or not adapter:
        return 400, {"success": False, "message": "Missing required fields: env, adapter"}

    # Validate adapter name to prevent path traversal
    if not re.match(r"^[a-z][a-z0-9-]*$", adapter):
        return 400, {"success": False, "message": "Invalid adapter name"}

    try:
        e = env
        q = _quote_env_value
        today = date.today().isoformat()

        env_content = f"""# Sorta.Fit -- Environment Configuration
# Generated by setup wizard on {today}
# Do NOT commit .env to version control.

# =============================================================================
# Board Connection
# =============================================================================

BOARD_ADAPTER={q(e.get('BOARD_ADAPTER', ''))}
BOARD_DOMAIN={q(e.get('BOARD_DOMAIN', ''))}
BOARD_API_TOKEN={q(e.get('BOARD_API_TOKEN', ''))}
BOARD_PROJECT_KEY={q(e.get('BOARD_PROJECT_KEY', ''))}
BOARD_EMAIL={q(e.get('BOARD_EMAIL', ''))}

# =============================================================================
# Target Repository
# =============================================================================

# Absolute path to the repository sorta.fit operates on
{('TARGET_REPO=' + q(e['TARGET_REPO'])) if e.get('TARGET_REPO') else '# TARGET_REPO='}

# =============================================================================
# Git
# =============================================================================

GIT_BASE_BRANCH={q(e.get('GIT_BASE_BRANCH', 'main'))}
GIT_RELEASE_BRANCH={q(e.get('GIT_RELEASE_BRANCH', ''))}

# =============================================================================
# Runner Behavior
# =============================================================================

# Seconds between polling cycles
POLL_INTERVAL={e.get('POLL_INTERVAL', '3600')}

# Maximum cards per cycle for each runner
MAX_CARDS_REFINE={e.get('MAX_CARDS_REFINE', '5')}
MAX_CARDS_ARCHITECT={e.get('MAX_CARDS_ARCHITECT', '5')}
MAX_CARDS_CODE={e.get('MAX_CARDS_CODE', '2')}
MAX_CARDS_REVIEW={e.get('MAX_CARDS_REVIEW', '10')}
MAX_CARDS_TRIAGE={e.get('MAX_CARDS_TRIAGE', '5')}
MAX_CARDS_BOUNCE={e.get('MAX_CARDS_BOUNCE', '10')}
MAX_CARDS_MERGE={e.get('MAX_CARDS_MERGE', '10')}

# Merge strategy: merge, squash, or rebase
MERGE_STRATEGY={e.get('MERGE_STRATEGY', 'merge')}

# Comma-separated list of runners to run
RUNNERS_ENABLED={e.get('RUNNERS_ENABLED', 'refine,code')}

# =============================================================================
# Claude Agent Configuration
# =============================================================================

CLAUDE_AGENT={e.get('CLAUDE_AGENT', '')}

# =============================================================================
# Runner Lane Routing (status IDs from your board)
# =============================================================================

RUNNER_REFINE_FROM={e.get('RUNNER_REFINE_FROM', '')}
RUNNER_REFINE_TO={e.get('RUNNER_REFINE_TO', '')}
RUNNER_REFINE_AGENT={e.get('RUNNER_REFINE_AGENT', '')}

RUNNER_ARCHITECT_FROM={e.get('RUNNER_ARCHITECT_FROM', '')}
RUNNER_ARCHITECT_TO={e.get('RUNNER_ARCHITECT_TO', '')}
RUNNER_ARCHITECT_AGENT={e.get('RUNNER_ARCHITECT_AGENT', '')}

RUNNER_CODE_FROM={e.get('RUNNER_CODE_FROM', '')}
RUNNER_CODE_TO={e.get('RUNNER_CODE_TO', '')}
RUNNER_CODE_AGENT={e.get('RUNNER_CODE_AGENT', '')}

RUNNER_REVIEW_FROM={e.get('RUNNER_REVIEW_FROM', '')}
RUNNER_REVIEW_TO={e.get('RUNNER_REVIEW_TO', '')}
RUNNER_REVIEW_AGENT={e.get('RUNNER_REVIEW_AGENT', '')}

RUNNER_TRIAGE_FROM={e.get('RUNNER_TRIAGE_FROM', '')}
RUNNER_TRIAGE_TO={e.get('RUNNER_TRIAGE_TO', '')}
RUNNER_TRIAGE_AGENT={e.get('RUNNER_TRIAGE_AGENT', '')}

RUNNER_BOUNCE_FROM={e.get('RUNNER_BOUNCE_FROM', '')}
RUNNER_BOUNCE_TO={e.get('RUNNER_BOUNCE_TO', '')}

RUNNER_MERGE_FROM={e.get('RUNNER_MERGE_FROM', '')}
RUNNER_MERGE_TO={e.get('RUNNER_MERGE_TO', '')}

RUNNER_DOCUMENTER_FROM={e.get('RUNNER_DOCUMENTER_FROM', '')}
RUNNER_DOCUMENTER_TO={e.get('RUNNER_DOCUMENTER_TO', '')}
RUNNER_DOCUMENTER_AGENT={e.get('RUNNER_DOCUMENTER_AGENT', '')}

MAX_BOUNCES={e.get('MAX_BOUNCES', '3')}

RUNNER_REVIEW_TO_REJECTED={e.get('RUNNER_REVIEW_TO_REJECTED', '')}

"""

        # Preserve keys from existing .env that the wizard doesn't manage
        env_path = sorta_root / ".env"
        managed_keys = set()
        for line in env_content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                if key:
                    managed_keys.add(key)

        preserved_lines = []
        if env_path.exists():
            from sortafit.config import parse_env_file
            existing = parse_env_file(env_path)
            for key, value in existing.items():
                if key not in managed_keys:
                    preserved_lines.append(f"{key}={_quote_env_value(value)}")

        if preserved_lines:
            env_content += "\n# =============================================================================\n"
            env_content += "# Additional Settings (preserved from previous config)\n"
            env_content += "# =============================================================================\n\n"
            env_content += "\n".join(preserved_lines) + "\n"

        env_path.write_text(env_content, encoding="utf-8")

        # Write adapter config if provided
        if adapter_config:
            status_entries = []
            trans_entries = []
            for key, value in adapter_config.items():
                formatted = f"{key}={_quote_env_value(str(value))}"
                if key.startswith("STATUS_"):
                    status_entries.append(formatted)
                elif key.startswith("TRANSITION_TO_"):
                    trans_entries.append(formatted)
                else:
                    status_entries.append(formatted)

            config_lines = [
                "#!/usr/bin/env bash",
                f"# {adapter} adapter configuration",
                f"# Generated by setup wizard on {today}",
                "",
                "# Status ID -> display name",
                *status_entries,
                "",
                "# How to transition a card TO each status (transition IDs)",
                *trans_entries,
                "",
            ]

            config_path = sorta_root / "adapters" / f"{adapter}.config.sh"
            config_path.write_text("\n".join(config_lines), encoding="utf-8")

        return 200, {"success": True, "message": "Configuration saved"}
    except Exception as e:
        return 500, {"success": False, "message": f"Failed to save config: {e}"}


def _handle_start_runner(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/start-runner — start the polling loop."""
    global _runner_process, _runner_pid

    if _runner_pid and _is_process_running(_runner_pid):
        return 200, {"success": True, "pid": _runner_pid, "message": "Runner is already active"}

    try:
        cwd = str(sorta_root)

        # Find Python executable
        python_cmd = sys.executable or "python"

        log_path = sorta_root / "runner.log"
        log_fd = open(log_path, "a")  # noqa: SIM115

        _runner_process = subprocess.Popen(
            [python_cmd, "-m", "sortafit"],
            cwd=cwd,
            stdout=log_fd,
            stderr=log_fd,
            stdin=subprocess.DEVNULL,
        )

        _runner_pid = _runner_process.pid
        return 200, {"success": True, "pid": _runner_pid}
    except Exception as e:
        return 500, {"success": False, "message": f"Failed to start runner: {e}"}


def _handle_stop_runner(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/stop-runner — stop the polling loop."""
    global _runner_process, _runner_pid

    if not _runner_pid or not _is_process_running(_runner_pid):
        _runner_process = None
        _runner_pid = None
        return 200, {"success": True, "message": "Runner is not active"}

    try:
        if _runner_process:
            _runner_process.terminate()
        _runner_process = None
        _runner_pid = None
        return 200, {"success": True, "message": "Runner stopped"}
    except Exception as e:
        return 500, {"success": False, "message": f"Failed to stop runner: {e}"}


def _handle_runner_status(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/runner-status — check if the runner is running."""
    global _runner_process, _runner_pid

    running = _is_process_running(_runner_pid)
    if not running:
        _runner_process = None
        _runner_pid = None
    return 200, {"running": running, "pid": _runner_pid}


def _handle_logs(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/logs — return tail of runner.log."""
    log_path = sorta_root / "runner.log"
    if not log_path.exists():
        return 200, {"success": True, "logs": "", "empty": True}

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        tail = "\n".join(lines[-200:])
        # Strip ANSI escape codes
        stripped = re.sub(r"\x1b\[[0-9;]*m", "", tail)
        return 200, {"success": True, "logs": stripped, "empty": False}
    except Exception as e:
        return 500, {"success": False, "message": f"Failed to read logs: {e}"}


# ── Dashboard helpers ──────────────────────────────────────────────────


def _tail_jsonl(file_path: Path, max_lines: int = 200) -> list[dict]:
    """Read the last N lines of a JSONL file, skipping malformed entries."""
    if not file_path.exists():
        return []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    lines = content.splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    result: list[dict] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            result.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return result



def _handle_events(body: dict, sorta_root: Path) -> tuple[int, dict]:
    """POST /api/events — return parsed event log entries."""
    limit = body.get("limit", 100)
    limit = min(max(1, int(limit)), 500)

    events_path = sorta_root / ".sorta" / "events.jsonl"
    all_events = _tail_jsonl(events_path, max_lines=500)
    total = len(all_events)
    result_events = all_events[-limit:] if len(all_events) > limit else all_events

    return 200, {
        "success": True,
        "events": result_events,
        "total": total,
    }


# ── Route table ─────────────────────────────────────────────────────────

API_ROUTES = {
    "/api/load-config": _handle_load_config,
    "/api/check-dependencies": _handle_check_dependencies,
    "/api/test-connection": _handle_test_connection,
    "/api/discover-board": _handle_discover_board,
    "/api/save-config": _handle_save_config,
    "/api/start-runner": _handle_start_runner,
    "/api/stop-runner": _handle_stop_runner,
    "/api/runner-status": _handle_runner_status,
    "/api/logs": _handle_logs,
    "/api/events": _handle_events,
}


# ── HTTP Handler ────────────────────────────────────────────────────────

class SetupHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the setup wizard."""

    # Class-level configuration (set before server starts)
    sorta_root: Path = Path(".")
    setup_dir: Path = Path(".")
    session_token: str = ""

    def log_message(self, format: str, *args: object) -> None:
        """Cleaner log output."""
        sys.stderr.write(f"[Setup] {args[0]}\n")

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        return json.loads(raw) if raw else {}

    def _require_auth(self) -> bool:
        """Validate X-Session-Token header (constant-time comparison)."""
        token = self.headers.get("X-Session-Token", "")
        if not token:
            return False
        return secrets.compare_digest(token, self.session_token)

    def _serve_index_html(self) -> None:
        """Serve index.html with session token injected."""
        html_path = self.setup_dir / "index.html"
        if not html_path.exists():
            self._send_json({"error": "index.html not found"}, 500)
            return

        html = html_path.read_text(encoding="utf-8")
        injected = html.replace("{{SESSION_TOKEN}}", self.session_token)
        body = injected.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, file_path: Path) -> None:
        """Serve a static file with appropriate content type."""
        if not file_path.exists() or not file_path.is_file():
            self._send_json({"error": "Not found"}, 404)
            return

        ext = file_path.suffix.lower()
        content_type = MIME_TYPES.get(ext, "application/octet-stream")
        body = file_path.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests — static files only."""
        parsed = urlparse(self.path)
        pathname = parsed.path

        if pathname.startswith("/api/"):
            self._send_json({"error": "Method not allowed — use POST"}, 405)
            return

        # Serve index.html for / and /index.html
        if pathname in ("/", "", "/index.html"):
            self._serve_index_html()
            return

        # Prevent directory traversal
        safe_path = os.path.normpath(pathname.lstrip("/"))
        if safe_path.startswith(".."):
            self._send_json({"error": "Forbidden"}, 403)
            return

        file_path = (self.setup_dir / safe_path).resolve()
        if not str(file_path).startswith(str(self.setup_dir.resolve())):
            self._send_json({"error": "Forbidden"}, 403)
            return

        self._serve_static(file_path)

    def do_POST(self) -> None:
        """Handle POST requests — API endpoints."""
        parsed = urlparse(self.path)
        pathname = parsed.path

        if not pathname.startswith("/api/"):
            self._send_json({"error": "Not found"}, 404)
            return

        # Require auth for all API endpoints
        if not self._require_auth():
            self._send_json({"error": "Unauthorized — provide X-Session-Token header"}, 401)
            return

        handler = API_ROUTES.get(pathname)
        if not handler:
            self._send_json({"error": f"Unknown API endpoint: {pathname}"}, 404)
            return

        try:
            body = self._read_body()
            status, data = handler(body, self.sorta_root)
            self._send_json(data, status)
        except Exception as e:
            sys.stderr.write(f"[Setup] Error in {pathname}: {e}\n")
            self._send_json({"error": str(e)}, 500)


# ── Server entry point ─────────────────────────────────────────────────

def main() -> None:
    """Start the setup wizard HTTP server."""
    port = int(os.environ.get("SETUP_PORT", "3456"))

    # Determine paths — sorta_root is the project root (parent of sortafit/)
    sorta_root = Path(__file__).resolve().parent.parent.parent
    setup_dir = sorta_root / "setup"

    if not setup_dir.exists():
        print(f"ERROR: setup/ directory not found at {setup_dir}", file=sys.stderr)
        sys.exit(1)

    if not (setup_dir / "index.html").exists():
        print(f"ERROR: setup/index.html not found at {setup_dir / 'index.html'}", file=sys.stderr)
        sys.exit(1)

    # Generate session token
    session_token = secrets.token_hex(32)

    # Configure handler class
    SetupHandler.sorta_root = sorta_root
    SetupHandler.setup_dir = setup_dir
    SetupHandler.session_token = session_token

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), SetupHandler)
    except OSError as e:
        if e.errno == 10048 or "Address already in use" in str(e):  # EADDRINUSE
            print(f"\nERROR: Port {port} is already in use.", file=sys.stderr)
            print("Another instance of the setup wizard may still be running.", file=sys.stderr)
            print("", file=sys.stderr)
            if platform.system() == "Windows":
                print("To fix this, run:", file=sys.stderr)
                print(f"  netstat -ano | findstr :{port}", file=sys.stderr)
                print("  taskkill /PID <pid> /F", file=sys.stderr)
            else:
                print(f"To fix this, run: lsof -ti:{port} | xargs kill", file=sys.stderr)
            print("", file=sys.stderr)
            print("Then try again.", file=sys.stderr)
            sys.exit(1)
        raise

    wizard_url = f"http://localhost:{port}"
    print(f"Sorta.Fit setup wizard running at {wizard_url}")
    print(f"Session token: {session_token}")
    print("(Token is injected into the page automatically — no copy-paste needed)")
    print("Press Ctrl+C to stop.\n")

    _open_browser(wizard_url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()
        # Stop runner if running
        if _runner_pid and _is_process_running(_runner_pid):
            try:
                if _runner_process:
                    _runner_process.terminate()
            except Exception:
                pass
        sys.exit(0)


if __name__ == "__main__":
    main()
