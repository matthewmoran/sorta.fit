# Sorta.Fit

Autonomous sprint execution powered by Claude Code. Sorta.Fit connects your issue board to Claude Code, polls for cards, and runs them through a configurable pipeline: spec refinement, implementation in isolated worktrees, PR creation, code review, and bug triage.

It runs in the background on your computer -- as long as it's on, your board keeps moving. Configure human review gates where you need them, or let it handle everything.

```
     [To Do] --refine--> [Refined] --architect--> [Architected] --you--> [Agent] --code--> [QA] --review--> [QA] --you--> [Done]
```

## Why Sorta.Fit

- **No API token costs** — Sorta.Fit uses the Claude Code CLI, not the API. You're running on your existing Claude subscription, not paying per-token.
- **Works with free tools** — Jira is free for up to 10 users. GitHub free tier covers everything you need. There's nothing extra to buy.
- **Runs on your machine** — No cloud infrastructure, no CI minutes, no hosted agents. It runs in the background on your computer using your local environment.
- **Works with your board** — Sorta.Fit connects to the board you already use. Jira Cloud is supported today, with Linear and GitHub Issues planned.

## How It Works

Sorta.Fit runs from **inside your project repository** so it can read your code, run your tests, and commit to branches. Drop the `sorta-fit` folder into your repo and run the setup from there.

1. **Loop** (`core/loop.sh`) starts a polling loop that fires every `POLL_INTERVAL` seconds.
2. Each cycle, it runs the enabled **runners** in order.
3. Each runner queries your issue board for cards in its pickup lane using the **adapter** interface.
4. For each card, the runner renders a **prompt template** with the card's details and passes it to Claude Code CLI.
5. Claude's output is written back to the board (updated descriptions, comments, transitions) and/or to GitHub (branches, PRs, reviews).

The adapter layer means Sorta.Fit is not tied to any one board. Implement the `board_*` functions for your platform and everything else works unchanged.

## Requirements

- **Git** (with Git Bash on Windows -- included with [Git for Windows](https://git-scm.com/downloads))
- **Node.js** ([nodejs.org](https://nodejs.org))
- **Claude Code CLI** ([claude.ai/code](https://claude.ai/code))
- **GitHub CLI** ([cli.github.com](https://cli.github.com))

On Windows, the runner and all scripts run inside Git Bash. Git for Windows includes this automatically.

### Claude Code Permissions

Sorta.Fit runs Claude Code in isolated worktrees to implement cards. Claude Code requires a `.claude/settings.local.json` file to have permission to write files, run commands, and use git. Without it, Claude will read the spec but won't be able to create any code.

Copy the example file to get started:

```bash
cp .claude/settings.local.json.example .claude/settings.local.json
```

This file is gitignored (it's user-specific) so each developer needs their own copy.

## Quick Start

### Setup Wizard (recommended)

**Windows:** Double-click `setup.bat`

**macOS / Linux:**
```bash
bash setup.sh
```

The wizard walks you through:
1. Checking dependencies
2. Connecting to your board and discovering statuses/transitions
3. Selecting which runners to enable
4. Configuring pickup and result lanes for each runner
5. Setting git and polling options

Once complete, it writes your `.env` and adapter config files.

### Manual Setup

1. Copy `.env.example` to `.env` and fill in your values.
2. Copy `adapters/jira.config.sh.example` to `adapters/jira.config.sh` and fill in your status and transition IDs (run `bash -c "source core/config.sh && source adapters/jira.sh && board_discover"` to find them).
3. Start the runner:

**Windows:** Double-click `run.bat` or run `bash run.sh` from Git Bash

**macOS / Linux:**
```bash
bash run.sh
```

For a complete reference of every configuration variable, see the [Setup Guide](docs/setup-guide.md).

## Runners

| Runner | What It Does | Default Flow |
|--------|-------------|-------------|
| `refine` | Generates structured spec from card | To Do --> Refined |
| `architect` | Analyzes codebase, enriches spec with implementation plan | Refined --> Architected |
| `code` | Implements card, creates branch and PR | Agent --> QA |
| `review` | Reviews PR diff, posts GitHub review | QA --> QA (stays) |
| `triage` | Analyzes bug report, writes triage to card | To Do --> Refined |
| `bounce` | Moves rejected PRs back for rework | QA --> Agent |
| `merge` | Merges approved PRs, transitions card to done | QA --> Done |
| `release-notes` | Generates grouped changelog from git history | Manual run |

Each runner's pickup and result lanes are configurable -- the defaults above match the suggested human-gates workflow.

Full documentation: [docs/runners.md](docs/runners.md)

## Workflow Options

### Human Gates (recommended)

You review specs before implementation starts, and review PRs before merging. The automated pipeline handles everything in between.

```
[To Do] --refine--> [Refined] --you--> [Agent] --code--> [QA] --review--> [QA] --you--> [Done]
```

### Fully Autonomous

Everything automated end-to-end. The merge runner closes the loop by merging approved PRs and transitioning cards to Done.

```
[To Do] --refine--> [Refined] --architect-->[Agent] --code--> [QA] --review--> [QA] --merge--> [Done]
```

## Supported Boards

| Board | Status |
|-------|--------|
| Jira Cloud | Ready |
| Linear | Planned |
| GitHub Issues | Planned |

Adapter documentation and how to write your own: [docs/adapters.md](docs/adapters.md)

## Safety

- **Worktrees** -- The `code` runner works in isolated git worktrees. Your main working tree is never modified.
- **Protected branches** -- Branches named `main`, `master`, `dev`, or `develop` are never checked out or pushed to.
- **Lock files** -- Prevents overlapping cycles if a previous run is still in progress.
- **No force push** -- Never uses `git push --force` or any destructive git operation.
- **Branch naming** -- All AI-created branches are prefixed with `claude/` and include the issue key.

## Contributing

Contributions are welcome. See [docs/contributing.md](docs/contributing.md) for the fork-branch-PR workflow, code style guide, and instructions for adding runners and adapters.

## License

AGPL-3.0 -- see [LICENSE](LICENSE).

---

*Dedicated to Becky — my favorite runner.*
