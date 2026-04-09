# Sorta.Fit -- Adapters

Adapters are the bridge between Sorta and your issue board. Each adapter implements a standard set of `board_*` functions that the runners call to read cards, update descriptions, post comments, and transition cards between lanes.

## How Adapters Are Loaded

The adapter is selected by the `BOARD_ADAPTER` environment variable in your `.env` file. When `core/config.sh` runs, it:

1. Reads `BOARD_ADAPTER` (e.g., `jira`)
2. Sources `adapters/{BOARD_ADAPTER}.sh` (e.g., `adapters/jira.sh`)
3. Sources `adapters/{BOARD_ADAPTER}.config.sh` (e.g., `adapters/jira.config.sh`)

If the adapter config file does not exist, a warning is printed directing you to copy from the `.example` file.

## The board_* Interface

Every adapter must implement the following functions. Runners depend on these exact function names and signatures.

### board_get_cards_in_status

```bash
board_get_cards_in_status <status_name> <max_results>
```

Query the board for cards in a given status. Output one card ID per line to stdout. The IDs are opaque -- they can be internal IDs (Jira: numeric IDs, Linear: UUIDs, GitHub Issues: issue numbers), as long as `board_get_card_key` can resolve them.

**Parameters:**
- `status_name` -- The status name to query (e.g., "To Do", "Agent", "QA")
- `max_results` -- Maximum number of cards to return

**Output:** One card ID per line, ordered by rank/priority.

### board_get_card_key

```bash
board_get_card_key <card_id>
```

Resolve a card ID to its human-readable key (e.g., `PROJ-42`). The key is used in branch names, commit messages, and comments.

**Parameters:**
- `card_id` -- The internal card ID (as returned by `board_get_cards_in_status`)

**Output:** Single line with the card key.

### board_get_card_title

```bash
board_get_card_title <card_key>
```

Get the title (summary) of a card.

**Parameters:**
- `card_key` -- The card key (e.g., `PROJ-42`)

**Output:** Single line with the card title.

### board_get_card_description

```bash
board_get_card_description <card_key>
```

Get the description body of a card as plain text. If the board stores rich text (Jira uses Atlassian Document Format), the adapter must convert it to plain text.

**Parameters:**
- `card_key` -- The card key

**Output:** Multi-line plain text description.

### board_get_card_comments

```bash
board_get_card_comments <card_key>
```

Get all comments on a card. Each comment should include the author, date, and body text. Comments are separated by `---` lines.

**Parameters:**
- `card_key` -- The card key

**Output:** Multi-line formatted comments. Example:
```
---
Author: Jane Doe
Date: 2026-01-15T10:30:00.000Z
This is the comment body text.
---
Author: John Smith
Date: 2026-01-16T14:00:00.000Z
Another comment.
```

### board_get_card_summary

```bash
board_get_card_summary <card_key>
```

Get a structured summary of a card including key, summary, status, type, and priority. Used for display purposes.

**Parameters:**
- `card_key` -- The card key

**Output:** Multi-line key-value pairs:
```
Key: PROJ-42
Summary: Add user authentication
Status: To Do
Type: Story
Priority: High
```

### board_update_description

```bash
board_update_description <card_key> <markdown_text>
```

Replace the card's description with new content. The adapter must convert the markdown text to the board's native format (e.g., Atlassian Document Format for Jira).

**Parameters:**
- `card_key` -- The card key
- `markdown_text` -- The new description in markdown format (can also be piped via stdin)

**Output:** None (API response may be printed but is not used).

### board_add_comment

```bash
board_add_comment <card_key> <comment_text>
```

Add a comment to a card.

**Parameters:**
- `card_key` -- The card key
- `comment_text` -- The comment body (can also be piped via stdin)

**Output:** None.

### board_transition

```bash
board_transition <card_key> <transition_id>
```

Move a card to a different status using a transition ID. Transition IDs are board-specific and defined in the adapter config file.

**Parameters:**
- `card_key` -- The card key
- `transition_id` -- The transition ID from the adapter config (Jira: numeric transition ID; Linear: target state UUID; GitHub Issues: target label name)

**Output:** None.

### board_discover

```bash
board_discover
```

Print all available statuses and transitions for the configured project. This is a setup helper -- it outputs the IDs needed to populate the adapter config file.

**Parameters:** None.

**Output:** Human-readable list of statuses and transitions with their IDs.

## Adapter Config Files

Each adapter has a config file that maps your board's workflow to Sorta's lane model. The config file defines shell variables for status IDs and transition IDs.

**File naming:** `adapters/{adapter_name}.config.sh`
**Example file:** `adapters/{adapter_name}.config.sh.example`

### Status Variables

Used by runners to query cards in specific lanes. Variables use the pattern `STATUS_<id>` where `<id>` is the board's status identifier. IDs must be sanitized to valid bash variable names (letters, digits, underscores only):

| Adapter | ID Format | Example |
|---------|-----------|---------|
| Jira | Numeric IDs | `STATUS_10000="To Do"` |
| Linear | UUIDs (hyphens replaced with underscores) | `STATUS_f2b1c3d4_5678_9abc_def0_1234567890ab="Todo"` |
| GitHub Issues | Label names (colons/hyphens replaced with underscores) | `STATUS_status_todo="To Do"` |

Define one variable per status in your workflow. The IDs come from `board_discover` output.

### Transition Variables

Used by runners to move cards between lanes. Variables use the pattern `TRANSITION_TO_<statusId>` where `<statusId>` is the sanitized target status ID:

| Adapter | Example | Notes |
|---------|---------|-------|
| Jira | `TRANSITION_TO_10070=5` | Value is a separate Jira transition ID |
| Linear | `TRANSITION_TO_f2b1c3d4_5678_...=f2b1c3d4-5678-...` | Value is the target state UUID (direct transitions) |
| GitHub Issues | `TRANSITION_TO_status_todo=status:todo` | Value is the real label name |

Define one variable per transition your workflow uses.

Not all statuses and transitions are required. Only define the ones your runners use. At minimum, you need the statuses and transitions for the lanes your enabled runners read from and write to.

## Writing a New Adapter

Follow these steps to add support for a new issue board.

### Step 1: Create the Adapter Script

Create `adapters/{name}.sh` with the standard shebang:

```bash
#!/usr/bin/env bash
# Sorta.Fit -- {Name} adapter
# Implements the board_* interface for {Name}

set -euo pipefail
```

### Step 2: Set Up Authentication

Read credentials from the environment variables set in `.env`:
- `BOARD_DOMAIN` -- The board's domain
- `BOARD_API_TOKEN` -- The API token
- `BOARD_PROJECT_KEY` -- The project identifier
- `BOARD_EMAIL` -- (optional) Account email, if the API needs it

```bash
AUTH_HEADER="Authorization: Bearer $BOARD_API_TOKEN"
BASE_URL="https://$BOARD_DOMAIN/api/v1"
```

### Step 3: Implement All board_* Functions

Implement every function listed in the interface section above. Use `curl` for HTTP requests and `node -e` for JSON parsing (Node.js is a guaranteed dependency).

Guidelines:
- Output to stdout only. Use `log_info`, `log_warn`, `log_error` from `core/utils.sh` for diagnostics (these go to stderr via color codes).
- Keep API calls minimal. Cache responses within a function if you need multiple fields from the same endpoint.
- Handle pagination if the board API requires it.
- Convert rich text to plain text in `board_get_card_description` and `board_get_card_comments`.
- Convert markdown to the board's native format in `board_update_description`.

### Step 4: Create the Config Example

Create `adapters/{name}.config.sh.example` with placeholder values and comments explaining how to find the real IDs:

```bash
#!/usr/bin/env bash
# {Name} adapter configuration
# Run board_discover to find these values for your project

# Status ID → display name
STATUS_10000="To Do"
STATUS_10070="Refined"
# ... add your project's status IDs

# How to transition a card TO each status
TRANSITION_TO_10000=11
TRANSITION_TO_10070=5
# ... add your project's transition IDs
```

### Step 5: Test with board_discover

Source your adapter and run the discover function:

```bash
source core/config.sh
source core/utils.sh
source adapters/{name}.sh
board_discover
```

Verify it outputs the correct statuses and transitions. Then test each function individually:

```bash
# Get cards in To Do
board_get_cards_in_status "To Do" 5

# Get a card's details
board_get_card_key "12345"
board_get_card_title "PROJ-1"
board_get_card_description "PROJ-1"
```

### Step 6: Run a Runner

Test end-to-end with a single runner against a test project:

```bash
bash runners/refine.sh
```

## Supported Adapters

### Jira (`adapters/jira.sh`)

The Jira adapter is the original reference implementation.

- **Authentication:** Basic auth using `BOARD_EMAIL:BOARD_API_TOKEN`
- **Base URL:** `https://{BOARD_DOMAIN}/rest/api/3`
- **Card queries:** Uses JQL via the `/search/jql` endpoint
- **Rich text:** Jira uses Atlassian Document Format (ADF). The adapter converts ADF to plain text for reading and markdown to ADF for writing
- **JSON parsing:** All JSON processing uses inline `node -e` scripts that read from stdin
- **Transitions:** Uses the `/issue/{key}/transitions` endpoint with numeric transition IDs
- **Status IDs:** Numeric (e.g., `10000`, `10070`)

### Linear (`adapters/linear.sh`)

- **Authentication:** Bearer token against the GraphQL API (`https://api.linear.app/graphql`)
- **Card queries:** GraphQL queries filtered by team key and workflow state ID
- **Rich text:** Native markdown -- no format conversion needed for descriptions or comments
- **Transitions:** Direct state-to-state updates via `issueUpdate` mutation; no intermediate transition IDs
- **Status IDs:** UUIDs (e.g., `f2b1c3d4-5678-9abc-def0-1234567890ab`); sanitized to underscores in config variable names
- **Card keys:** Uses Linear's identifier format (e.g., `ENG-123`)

### GitHub Issues (`adapters/github-issues.sh`)

- **Authentication:** Prefers `gh` CLI (handles auth automatically); falls back to `curl` with `BOARD_API_TOKEN` if `gh` is unavailable
- **Card queries:** REST API, filtering by label (e.g., `status:todo`)
- **Rich text:** Native markdown -- no conversion needed
- **Transitions:** Label swap -- removes existing `status:*` labels and adds the target label
- **Status IDs:** Label names (e.g., `status:todo`, `status:refined`); sanitized to underscores in config variable names
- **Card keys:** Issue numbers with `GH-` prefix (e.g., `GH-42`)
- **GitHub Enterprise:** Supported; set `BOARD_DOMAIN` to your GHE domain and the adapter derives the `/api/v3` base URL

For detailed usage, configuration examples, and setup instructions for each adapter, see [Board Adapters](features/board-adapters.md).
