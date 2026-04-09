# Custom Claude Agents

Sorta.Fit supports specifying custom Claude Code agents on a per-runner basis or globally. This lets each runner invoke a different pre-configured agent — for example, a specialized "code reviewer" agent for the review runner and a "spec writer" agent for the refine runner — instead of using the default Claude agent for everything.

## Overview

Agent configuration uses a two-tier hierarchy:

1. **Global default** (`CLAUDE_AGENT`) — applies to all runners unless overridden
2. **Per-runner override** (`RUNNER_<NAME>_AGENT`) — takes precedence over the global default for a specific runner

When neither is set, runners invoke `claude -p` without an `--agent` flag, preserving the default CLI behavior.

The `--agent` flag references a pre-configured Claude Code agent by name. Agents are managed separately via the `claude agent` CLI commands — Sorta.Fit only passes the name through.

## Usage

### Configuration via .env

Set a global agent for all runners:

```bash
CLAUDE_AGENT=my-custom-agent
```

Override for specific runners:

```bash
RUNNER_REFINE_AGENT=spec-writer
RUNNER_CODE_AGENT=senior-developer
RUNNER_REVIEW_AGENT=code-reviewer
```

All agent variables are optional. Leave them empty or unset to use the default Claude behavior.

### Available Per-Runner Variables

| Variable | Runner |
|----------|--------|
| `RUNNER_REFINE_AGENT` | refine |
| `RUNNER_ARCHITECT_AGENT` | architect |
| `RUNNER_CODE_AGENT` | code |
| `RUNNER_REVIEW_AGENT` | review |
| `RUNNER_TRIAGE_AGENT` | triage |
| `RUNNER_DOCUMENTER_AGENT` | documenter |
| `RUNNER_RELEASE_NOTES_AGENT` | release-notes |

The bounce and merge runners do not invoke Claude, so they have no agent configuration.

### Resolution Order

Each runner resolves its agent using this fallback chain:

```
RUNNER_<NAME>_AGENT  →  CLAUDE_AGENT  →  (no --agent flag)
```

In the runner scripts, this is expressed as:

```bash
"${RUNNER_REFINE_AGENT:-$CLAUDE_AGENT}"
```

### Setup Wizard

The setup wizard (`bash setup.sh`) includes agent configuration fields:

- A global **Claude Agent** text input in the settings step
- A per-runner **Claude Agent** text input on each runner's configuration card

Both values are saved to `.env` and loaded back when re-opening the wizard.

## API

### run_claude

```bash
run_claude <prompt_file> <result_file> [working_dir] [agent]
```

The 4th parameter is the agent name. When non-empty, `--agent <name>` is appended to the `claude -p` invocation. When empty or omitted, no `--agent` flag is passed.

Returns: `0` on success, `1` on failure, `2` on rate limit.

### run_claude_safe

```bash
run_claude_safe <prompt_file> <result_file> [working_dir] [agent]
```

Wrapper around `run_claude` that cleans up temp files on failure. Same parameters and return codes.

## Examples

### Specialized Agents Per Phase

Use different agents tuned for each phase of the pipeline:

```bash
# Global fallback
CLAUDE_AGENT=general-purpose

# Spec-writing agent with strong requirements-analysis skills
RUNNER_REFINE_AGENT=spec-writer

# Architecture-focused agent that knows your codebase patterns
RUNNER_ARCHITECT_AGENT=system-architect

# Coding agent with strict style enforcement
RUNNER_CODE_AGENT=senior-developer

# Review agent focused on security and correctness
RUNNER_REVIEW_AGENT=security-reviewer
```

### Single Global Agent

Apply one custom agent to all runners:

```bash
CLAUDE_AGENT=my-team-agent
```

All runners use `my-team-agent` unless individually overridden.

### Selective Override

Set a global default but override just one runner:

```bash
CLAUDE_AGENT=default-agent
RUNNER_CODE_AGENT=coding-specialist
```

- refine, architect, review, triage, documenter, release-notes: use `default-agent`
- code: uses `coding-specialist`
