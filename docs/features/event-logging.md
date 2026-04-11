# Event Logging

## Overview

Sorta.Fit writes structured JSON events to an append-only log file during runner execution. Every significant automation action -- runner lifecycle, card processing, PR operations, transitions, Claude invocations -- is recorded as a machine-readable event. This provides telemetry for debugging, auditing, and analytics and observability.

Events are written to `$SORTA_ROOT/.sorta/events.jsonl` in [JSON Lines](https://jsonlines.org/) format (one JSON object per line). The `.sorta/` directory is local and git-ignored -- event logs are never committed to the repository.

## Usage

### Configuration

Event logging is enabled by default. To disable it, set `EVENT_LOGGING=off` in `.env`:

```bash
# Event logging: writes structured JSON events to .sorta/events.jsonl
# Set to "off" to disable event logging entirely (default: on)
EVENT_LOGGING=off
```

When disabled, the `log_event` function returns immediately without creating any files or directories.

### Viewing Events

Events are plain JSONL -- read them with any tool that handles newline-delimited JSON:

```bash
# View recent events
tail -20 .sorta/events.jsonl

# Pretty-print the last event
tail -1 .sorta/events.jsonl | node -e "process.stdin.on('data',d=>console.log(JSON.stringify(JSON.parse(d),null,2)))"

# Filter by event type
node -e "
  require('fs').readFileSync('.sorta/events.jsonl','utf8')
    .trim().split('\n')
    .map(JSON.parse)
    .filter(e => e.event === 'card_processed')
    .forEach(e => console.log(JSON.stringify(e)))
"
```

### Correlation with Cycle IDs

Every polling cycle generates a unique `CYCLE_ID` (format: `<pid>-<unix_timestamp>`) that is included in all events emitted during that cycle. Use this to trace the complete history of a single automation run:

```bash
# Find all events from a specific cycle
node -e "
  require('fs').readFileSync('.sorta/events.jsonl','utf8')
    .trim().split('\n')
    .map(JSON.parse)
    .filter(e => e.cycle_id === '12345-1712678400')
    .forEach(e => console.log(JSON.stringify(e)))
"
```

## API

### `log_event`

Appends a single JSON event to the JSONL log file.

```bash
log_event <event_type> [key=value ...]
```

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `event_type` | Required. The event name (e.g., `runner_started`, `card_processed`) |
| `key=value` | Optional. One or more data fields included in the event's `data` object |

**Behavior:**

- Creates `$SORTA_ROOT/.sorta/` if it does not exist
- Generates JSON using `node -e` with `JSON.stringify` for safe escaping
- Appends atomically via a single `>>` write
- Returns immediately when `EVENT_LOGGING` is not `on`
- Non-blocking and failure-tolerant -- wrapped in `{ ... } || true` so a write failure never aborts a runner under `set -e`
- Produces no stdout or stderr output, so it is safe to use inside functions whose return value is captured with `$()`

**Environment variables read:**

| Variable | Description |
|----------|-------------|
| `EVENT_LOGGING` | Must be `on` for events to be written (default: `on`) |
| `RUNNER_NAME` | Included as the `runner` field (default: `unknown`) |
| `CYCLE_ID` | Included as `cycle_id` when set (exported by `core/loop.sh`) |
| `SORTA_ROOT` | Base directory for the `.sorta/` event log directory |

### Event Schema

Every event contains these fields:

```json
{
  "timestamp": "2026-04-09T14:32:01.123Z",
  "event": "card_processed",
  "runner": "refine",
  "cycle_id": "12345-1712678400",
  "data": {
    "card_key": "SF-42",
    "outcome": "success",
    "runner": "refine"
  }
}
```

| Field | Type | Always present | Description |
|-------|------|----------------|-------------|
| `timestamp` | string | Yes | ISO 8601 UTC timestamp |
| `event` | string | Yes | Event type identifier |
| `runner` | string | Yes | Runner name or `"loop"` for cycle events |
| `cycle_id` | string | When in a cycle | Correlates events within a single polling cycle |
| `data` | object | When key-value pairs provided | Event-specific fields |

## Event Types

### Cycle Events

Emitted by `core/loop.sh`:

| Event | Data fields | Description |
|-------|-------------|-------------|
| `cycle_started` | -- | Emitted at the start of each polling cycle |
| `cycle_completed` | `duration_s` | Emitted when all runners finish; includes elapsed time in seconds |

### Runner Lifecycle Events

Emitted by each runner at the start and end of execution:

| Event | Data fields | Description |
|-------|-------------|-------------|
| `runner_started` | -- | Runner begins processing |
| `runner_completed` | `cards_processed` | Runner finishes; count of successfully processed cards |

### Card Events

| Event | Data fields | Description |
|-------|-------------|-------------|
| `card_processed` | `card_key`, `outcome`, `runner` | Per-card result. Outcome is `success`, `skipped`, or `failed` |
| `card_transitioned` | `card_key`, `target_status`, `transition_configured` | Emitted by `runner_transition` when moving a card between lanes |

### Claude Events

Emitted by `run_claude_safe` in `core/runner-lib.sh`:

| Event | Data fields | Description |
|-------|-------------|-------------|
| `claude_started` | -- | Claude Code invocation begins |
| `claude_completed` | `duration_s`, `exit_code` | Invocation finishes with duration and exit code |

### Domain Events

Emitted by specialized runners for significant workflow actions:

| Event | Emitted by | Data fields | Description |
|-------|-----------|-------------|-------------|
| `pr_opened` | code, documenter | `card_key`, `pr_url` | New pull request created |
| `pr_updated` | code | `card_key`, `pr_url` | Existing PR updated (rework push) |
| `pr_merged` | merge | `card_key`, `pr_url`, `merge_strategy` | Pull request merged |
| `bounce_triggered` | bounce | `card_key`, `bounce_count` | Card bounced back for rework |
| `bounce_escalated` | bounce | `card_key`, `bounce_count`, `max_bounces` | Card hit max bounce limit |

## Examples

### Typical Event Sequence

A normal cycle processing one card through the refine runner produces this sequence:

```
cycle_started
  runner_started          (runner: refine)
    card_processed        (outcome: success, card_key: SF-42)
    card_transitioned     (card_key: SF-42, transition_configured: true)
  runner_completed        (cards_processed: 1)
cycle_completed           (duration_s: 12)
```

### Adding Events to a Custom Runner

When writing a new runner, follow the standard event pattern:

```bash
RUNNER_NAME="myrunner"
export RUNNER_NAME
CARDS_PROCESSED=0

log_event runner_started

# ... card processing loop ...
  log_event card_processed card_key="$ISSUE_KEY" outcome="success" runner="$RUNNER_NAME"
  CARDS_PROCESSED=$((CARDS_PROCESSED + 1))
# ... end loop ...

log_event runner_completed cards_processed="$CARDS_PROCESSED"
```

Set `RUNNER_NAME` immediately after the `source` block, before any processing. Emit `card_processed` with the appropriate `outcome` value (`success`, `skipped`, or `failed`) for each card. Only increment `CARDS_PROCESSED` on success -- skipped cards are tracked individually via their `card_processed` events but do not count toward the runner's total.

### File Location

The event log is always at `$SORTA_ROOT/.sorta/events.jsonl`. In test environments, `SORTA_ROOT` points to a temporary directory, so event files are naturally isolated.

**Note:** The `release-notes.sh` runner is excluded from event logging because it runs manually outside the polling loop and has no `CYCLE_ID` for correlation. A future card may add standalone event support.
