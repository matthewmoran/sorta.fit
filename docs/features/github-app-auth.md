# GitHub App Authentication

Sorta.Fit can authenticate as a GitHub App instead of your personal account. When configured, all Git pushes, PR creation, and PR reviews show as a bot user (e.g., `sorta-fit-bot[bot]`), which solves the key problem: GitHub does not allow you to approve your own pull requests, so a bot identity lets the review runner post approvals and change requests on PRs that the code runner created.

## Overview

Without a GitHub App, Sorta.Fit uses whatever authentication the `gh` CLI has configured -- typically your personal GitHub account. This works for most operations, but the review runner cannot approve PRs created by the same account. With a GitHub App:

- PRs are created and pushed as `sorta-fit-bot[bot]` (or whatever you name the app)
- The review runner can approve or request changes, since the PR author is the bot, not you
- You retain full control -- the app only has the permissions you grant
- Token refresh is automatic -- the system generates short-lived tokens each polling cycle

## Setup

### 1. Register a GitHub App

Go to **Settings > Developer settings > GitHub Apps > New GitHub App** on GitHub.

- **Name:** Choose a name (e.g., `sorta-fit-bot`). This appears as the commit/PR author.
- **Homepage URL:** Any valid URL (required by GitHub but not used).
- **Webhooks:** Uncheck "Active" -- Sorta.Fit polls the board, it does not listen for GitHub events.
- **Callback URLs:** Leave empty -- not needed for this use case.

### 2. Set Permissions

Under **Repository permissions**, grant only what Sorta.Fit needs:

| Permission | Access | Purpose |
|------------|--------|---------|
| Contents | Read & Write | Push branches to the repository |
| Pull requests | Read & Write | Create PRs, post reviews, merge |

No other permissions are required. Leave everything else at "No access".

### 3. Install the App

After creating the app:

1. Go to the app's settings page and click **Install App**
2. Select the repository (or repositories) Sorta.Fit operates on
3. Confirm the installation

### 4. Generate Credentials

You need three values from the GitHub App settings:

1. **App ID** -- Shown on the app's general settings page (a numeric ID)
2. **Private key** -- Click **Generate a private key** on the settings page. Save the downloaded `.pem` file in a secure location (it is gitignored by default)
3. **Installation ID** -- Go to the app's installations page. The installation ID is the numeric value in the URL when you click on your installation (e.g., `https://github.com/settings/installations/12345678` -- the ID is `12345678`)

### 5. Configure Sorta.Fit

Add the three values to your `.env` file:

```bash
GH_APP_ID=your-app-id
GH_APP_INSTALLATION_ID=your-installation-id
GH_APP_PRIVATE_KEY_PATH=/absolute/path/to/private-key.pem
```

- `GH_APP_ID` -- The numeric App ID from the app settings page
- `GH_APP_INSTALLATION_ID` -- The numeric Installation ID from the installations page
- `GH_APP_PRIVATE_KEY_PATH` -- Absolute path to the `.pem` private key file

All three variables must be set for GitHub App authentication to activate. If any are empty or missing, the system silently falls back to default `gh` CLI authentication.

## How It Works

### Token Generation

GitHub App authentication uses a two-step process, handled automatically by `core/gh-token.js`:

1. **JWT creation** -- A JSON Web Token is signed with the app's private key (RS256 algorithm). The JWT is valid for 10 minutes and includes a 60-second clock skew allowance.
2. **Token exchange** -- The JWT is sent to the GitHub API (`POST /app/installations/{id}/access_tokens`) and exchanged for a short-lived installation access token.

The resulting token is exported as `GH_TOKEN`, which the `gh` CLI and `git push` pick up automatically.

### Refresh Cycle

The token is refreshed once per polling cycle in `core/loop.sh`, before any runners execute. If the refresh fails, the system logs a warning and falls back to default `gh` CLI authentication for that cycle. This means a transient GitHub API error won't halt the entire automation -- it gracefully degrades.

```
Poll cycle starts
  --> refresh_gh_token()        # Generate new installation token
  --> GH_TOKEN exported          # gh CLI and git push use bot identity
  --> Runners execute            # All GitHub operations use the bot token
  --> Sleep POLL_INTERVAL
```

### Fallback Behavior

| Scenario | Behavior |
|----------|----------|
| All `GH_APP_*` variables set | Authenticates as GitHub App bot |
| Any `GH_APP_*` variable empty/missing | Uses default `gh` CLI auth (personal account) |
| Private key file not found | Logs error, falls back to default auth |
| GitHub API rejects the JWT | Logs error, falls back to default auth for that cycle |

## Security

- **Private key storage** -- The `.pem` file should be stored outside the repository or in the project root (where `*.pem` is gitignored by default). Never commit private keys.
- **Short-lived tokens** -- Installation tokens are generated fresh each polling cycle. They expire after 1 hour (GitHub's limit), but Sorta.Fit generates a new one every cycle regardless.
- **Minimal permissions** -- Only Contents (read/write) and Pull requests (read/write) are required. Grant nothing else.
- **File permissions** -- On macOS/Linux, restrict the private key file: `chmod 600 /path/to/private-key.pem`

## Examples

### Typical .env Configuration

```bash
# GitHub App (bot identity for PRs and reviews)
GH_APP_ID=123456
GH_APP_INSTALLATION_ID=78901234
GH_APP_PRIVATE_KEY_PATH=/home/user/.keys/sorta-fit-bot.pem
```

### Verifying the Setup

After configuring, run a single runner and check that the GitHub operations show the bot identity:

```bash
bash runners/review.sh
```

On the resulting PR review, the author should appear as `sorta-fit-bot[bot]` (or whatever you named your app) instead of your personal account.

### Testing Token Generation Manually

```bash
# Source the config and auth modules, then refresh
source core/config.sh
source core/utils.sh
source core/gh-auth.sh
refresh_gh_token
echo "Token starts with: ${GH_TOKEN:0:8}..."
```

If successful, `GH_TOKEN` is set and the `gh` CLI will use the bot identity for subsequent commands in that shell session.
