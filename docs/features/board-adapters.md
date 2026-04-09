# Board Adapters

Sorta.Fit supports three issue board adapters: **Jira**, **Linear**, and **GitHub Issues**. Each adapter implements the same `board_*` function interface, so all runners work identically regardless of which board you use.

## Overview

The adapter layer translates between Sorta.Fit's generic lane model and your board's API. When you set `BOARD_ADAPTER` in `.env`, the system dynamically loads the corresponding adapter script and config file. Runners never interact with board APIs directly -- they call `board_get_cards_in_status`, `board_transition`, etc., and the adapter handles the rest.

```
Runners  -->  board_* interface  -->  Adapter  -->  Board API
                                        |
                                  Config (.config.sh)
```

## Jira Adapter

### Authentication

Jira uses Basic authentication with your Atlassian email and API token.

### Configuration

```bash
BOARD_ADAPTER=jira
BOARD_DOMAIN=mycompany.atlassian.net
BOARD_EMAIL=you@example.com
BOARD_API_TOKEN=your-jira-api-token
BOARD_PROJECT_KEY=PROJ
```

- `BOARD_DOMAIN` -- Your Atlassian Cloud domain
- `BOARD_EMAIL` -- Required (Jira-only; not used by other adapters)
- `BOARD_PROJECT_KEY` -- Jira project key (e.g., `PROJ`, `ENG`)

### Status IDs

Jira uses numeric status IDs (e.g., `10000`, `10070`). Transition IDs are separate numeric values specific to your project's workflow. Run `board_discover` or the setup wizard to find them.

### Notes

- Descriptions use Atlassian Document Format (ADF) internally; the adapter converts between ADF and markdown automatically
- Comments also use ADF and are converted on read/write

## Linear Adapter

### Authentication

Linear uses bearer token authentication against its GraphQL API.

### Configuration

```bash
BOARD_ADAPTER=linear
BOARD_DOMAIN=api.linear.app
BOARD_API_TOKEN=your-linear-api-key
BOARD_PROJECT_KEY=TEAM
```

- `BOARD_DOMAIN` -- Use `api.linear.app` (the default GraphQL endpoint)
- `BOARD_API_TOKEN` -- Required. Generate from Linear Settings > API > Personal API keys
- `BOARD_PROJECT_KEY` -- Your Linear team key (e.g., `ENG`, `PROD`)

### Status IDs

Linear uses UUID workflow state IDs (e.g., `f2b1c3d4-5678-9abc-def0-1234567890ab`). In config files, hyphens are replaced with underscores for bash variable name compatibility:

```bash
# Config key uses underscores; transition value uses the real UUID
STATUS_f2b1c3d4_5678_9abc_def0_1234567890ab="Todo"
TRANSITION_TO_f2b1c3d4_5678_9abc_def0_1234567890ab=f2b1c3d4-5678-9abc-def0-1234567890ab
```

In `.env` lane routing, use the **real UUID with hyphens**:

```bash
RUNNER_REFINE_FROM=f2b1c3d4-5678-9abc-def0-1234567890ab
RUNNER_REFINE_TO=a1b2c3d4-5678-9abc-def0-1234567890ab
```

The system sanitizes these automatically when looking up config variables.

### Transitions

Linear allows direct state-to-state transitions (no intermediate transition IDs like Jira). The `TRANSITION_TO_<stateId>` value is the target state UUID itself.

### Notes

- Descriptions and comments are native markdown -- no format conversion needed
- Linear has no built-in issue types (Bug, Feature, etc.). `board_get_card_type` uses labels as a type proxy. If you use the triage runner's `RUNNER_TRIAGE_FILTER_TYPE`, you need a matching label on your Linear issues
- Sub-issues are treated as flat (no parent/child traversal)
- Card keys use Linear's identifier format (e.g., `ENG-123`)

## GitHub Issues Adapter

### Authentication

The GitHub Issues adapter supports two authentication methods:

1. **`gh` CLI (preferred)** -- If the `gh` CLI is installed and authenticated (`gh auth login`), the adapter uses it automatically. No API token needed.
2. **Personal access token** -- Set `BOARD_API_TOKEN` with a GitHub PAT for environments where `gh` isn't authenticated.

The adapter checks `gh auth status` at startup and falls back to the token-based approach if the CLI isn't available or authenticated.

### Configuration

```bash
BOARD_ADAPTER=github-issues
BOARD_DOMAIN=github.com
BOARD_API_TOKEN=your-github-pat-or-leave-empty-for-gh-cli
BOARD_PROJECT_KEY=owner/repo
```

- `BOARD_DOMAIN` -- Use `github.com` for GitHub.com. For GitHub Enterprise, use your GHE domain (e.g., `github.mycompany.com`); the adapter derives the correct API base URL (`/api/v3` prefix)
- `BOARD_API_TOKEN` -- Optional if using `gh` CLI auth
- `BOARD_PROJECT_KEY` -- Repository in `owner/repo` format (e.g., `myorg/myproject`)

### Status IDs

GitHub Issues uses **labels** to represent lanes. The convention is a `status:` prefix (e.g., `status:todo`, `status:refined`, `status:in-progress`). In config files, colons and hyphens are replaced with underscores:

```bash
# Config key uses underscores; transition value uses the real label name
STATUS_status_todo="To Do"
STATUS_status_in_progress="In Progress"
TRANSITION_TO_status_todo=status:todo
TRANSITION_TO_status_in_progress=status:in-progress
```

In `.env` lane routing, use the **real label names**:

```bash
RUNNER_REFINE_FROM=status:todo
RUNNER_REFINE_TO=status:refined
```

### Transitions

Transitioning a GitHub issue means swapping labels -- the adapter removes all existing `status:*` labels and adds the target status label. Any status can transition to any other status.

### Setting Up Labels

Before using the adapter, create `status:` labels on your GitHub repository for each lane in your workflow. For example:

- `status:todo`
- `status:refined`
- `status:architected`
- `status:agent`
- `status:in-progress`
- `status:qa`
- `status:done`

### Notes

- Descriptions and comments are native markdown -- no format conversion
- Card keys use the `GH-` prefix (e.g., `GH-42`) for compatibility with branch names and shell contexts
- The adapter filters out pull requests from issue listings (GitHub's Issues API returns both)
- `board_get_card_type` checks issue labels for type indicators (`bug`, `feature`, `task`) and returns the first match
- Pagination is capped at 100 results per API page

## Setup Wizard

The setup wizard (`bash setup.sh`) supports all three adapters. When you select an adapter in the dropdown, the form dynamically adjusts:

- **Jira** -- Shows email, domain, and project key fields
- **Linear** -- Hides the email field; sets domain hint to `api.linear.app`; project key hint shows team key format
- **GitHub Issues** -- Hides the email field; API token is optional; project key hint shows `owner/repo` format

Both **Test Connection** and **Discover Board** work for all three adapters. Discovery outputs the status IDs and transition mappings you need for your config file, including the sanitized variable names ready to copy into `adapters/{adapter}.config.sh`.

## Discovering Status IDs

Every adapter implements `board_discover`, which prints the available statuses and transitions for your project. You can run it from the setup wizard or directly:

```bash
# Source the config and adapter, then discover
bash -c "source core/config.sh && board_discover"
```

The output includes both the real IDs (for `.env` lane routing) and the sanitized config variable names (for the adapter config file).

## Examples

### Linear -- Typical Pipeline

```bash
BOARD_ADAPTER=linear
BOARD_DOMAIN=api.linear.app
BOARD_PROJECT_KEY=ENG

RUNNERS_ENABLED=refine,architect,code,review,bounce,merge

# Use real UUIDs from board_discover output
RUNNER_REFINE_FROM=abc12345-1111-2222-3333-444444444444
RUNNER_REFINE_TO=abc12345-1111-2222-3333-555555555555
RUNNER_CODE_FROM=abc12345-1111-2222-3333-666666666666
RUNNER_CODE_TO=abc12345-1111-2222-3333-777777777777
```

### GitHub Issues -- Typical Pipeline

```bash
BOARD_ADAPTER=github-issues
BOARD_DOMAIN=github.com
BOARD_PROJECT_KEY=myorg/myproject

RUNNERS_ENABLED=refine,architect,code,review,bounce,merge

# Use label names from board_discover output
RUNNER_REFINE_FROM=status:todo
RUNNER_REFINE_TO=status:refined
RUNNER_CODE_FROM=status:agent
RUNNER_CODE_TO=status:qa
RUNNER_REVIEW_FROM=status:qa
```
