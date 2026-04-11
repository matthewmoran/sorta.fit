"""Sorta.Fit configuration loader — port of core/config.sh"""
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file. Matches the bash loader behavior exactly."""
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes (matching bash: value="${value%\"}"; value="${value#\"}")
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        env[key] = value
    return env


def load_adapter_config(config_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Parse an adapter .config.sh file for STATUS_* and TRANSITION_TO_* mappings."""
    statuses = {}
    transitions = {}
    if not config_path.exists():
        return statuses, transitions
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip('"')
        if key.startswith("STATUS_"):
            statuses[key] = value
        elif key.startswith("TRANSITION_TO_"):
            transitions[key] = value
    return statuses, transitions


@dataclass
class Config:
    """All Sorta.Fit configuration — typed equivalent of the 40+ env vars."""

    # Required
    board_adapter: str = ""
    board_domain: str = ""
    board_project_key: str = ""
    board_api_token: str = ""
    board_email: str = ""
    target_repo: str = ""

    # Git
    git_base_branch: str = "main"
    git_release_branch: str = ""

    # Polling
    poll_interval: int = 3600
    runners_enabled: list[str] = field(default_factory=lambda: ["refine", "code"])
    max_skip_retries: int = 3

    # Per-runner max cards
    max_cards_refine: int = 5
    max_cards_architect: int = 5
    max_cards_code: int = 2
    max_cards_review: int = 10
    max_cards_triage: int = 5
    max_cards_bounce: int = 10
    max_cards_merge: int = 10
    max_cards_documenter: int = 5

    # Runner lane routing
    runner_refine_from: str = ""
    runner_refine_to: str = ""
    runner_refine_filter_type: str = ""
    runner_refine_agent: str = ""

    runner_architect_from: str = ""
    runner_architect_to: str = ""
    runner_architect_agent: str = ""

    runner_code_from: str = ""
    runner_code_to: str = ""
    runner_code_agent: str = ""

    runner_review_from: str = ""
    runner_review_to: str = ""
    runner_review_to_rejected: str = ""
    runner_review_agent: str = ""

    runner_triage_from: str = ""
    runner_triage_to: str = ""
    runner_triage_filter_type: str = "Bug"
    runner_triage_agent: str = ""

    runner_bounce_from: str = ""
    runner_bounce_to: str = ""
    max_bounces: int = 3
    runner_bounce_escalate: str = ""

    runner_merge_from: str = ""
    runner_merge_to: str = ""
    merge_strategy: str = "merge"

    runner_documenter_from: str = ""
    runner_documenter_to: str = ""
    docs_dir: str = "docs"
    docs_organize_by: str = "feature"
    runner_documenter_agent: str = ""

    runner_release_notes_agent: str = ""

    # Review
    review_max_diff_chars: int = 100000

    # Claude
    claude_agent: str = ""

    # GitHub App auth
    gh_app_id: str = ""
    gh_app_installation_id: str = ""
    gh_app_private_key_path: str = ""
    gh_app_token: str = ""  # set at runtime by refresh_gh_token, not from .env

    # Event logging
    event_logging: str = "on"

    # Adapter config (loaded from .config.sh)
    adapter_statuses: dict[str, str] = field(default_factory=dict)
    adapter_transitions: dict[str, str] = field(default_factory=dict)

    # Resolved at load time
    sorta_root: str = ""


def _git_bash_to_windows(path: str) -> str:
    """Convert Git Bash paths (/c/Repos/...) to Windows paths (C:/Repos/...)."""
    if len(path) >= 3 and path[0] == "/" and path[1].isalpha() and path[2] == "/":
        return f"{path[1].upper()}:{path[2:]}"
    return path


def _resolve_target_repo(raw: str, sorta_root: Path) -> str:
    """Validate TARGET_REPO or infer from cwd."""
    if raw:
        raw = _git_bash_to_windows(raw)
        repo_path = Path(raw)
        if not repo_path.is_absolute():
            raise ConfigError(f"TARGET_REPO must be an absolute path (got: {raw})")
        if not repo_path.is_dir():
            raise ConfigError(f"TARGET_REPO does not exist: {raw}")
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--git-dir"],
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            raise ConfigError(f"TARGET_REPO is not a git repository: {raw}")
        return raw

    # Fallback: infer from cwd
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode == 0:
        return result.stdout.strip()
    raise ConfigError(
        "TARGET_REPO is not set and current directory is not inside a git repository."
    )


def load_config(env_path: Path | None = None, sorta_root: Path | None = None) -> Config:
    """Load configuration from .env file and validate."""
    if sorta_root is None:
        sorta_root = Path(__file__).resolve().parent.parent

    if env_path is None:
        env_path = sorta_root / ".env"

    if not env_path.exists():
        raise ConfigError(f".env not found at {env_path}. Run the setup wizard first.")

    env = parse_env_file(env_path)

    # Required fields
    adapter = env.get("BOARD_ADAPTER", "")
    if not adapter:
        raise ConfigError("BOARD_ADAPTER not set (jira, linear, github-issues)")
    if adapter not in ("jira", "linear", "github-issues"):
        raise ConfigError(f"Unknown adapter: {adapter}")

    domain = env.get("BOARD_DOMAIN", "")
    if not domain:
        raise ConfigError("BOARD_DOMAIN not set")
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9.-]+[a-zA-Z0-9]$", domain):
        raise ConfigError(f"Invalid BOARD_DOMAIN: {domain}")

    project_key = env.get("BOARD_PROJECT_KEY", "")
    if not project_key:
        raise ConfigError("BOARD_PROJECT_KEY not set")

    api_token = env.get("BOARD_API_TOKEN", "")
    if not api_token and adapter != "github-issues":
        raise ConfigError(f"BOARD_API_TOKEN not set (required for {adapter} adapter)")

    target_repo = _resolve_target_repo(env.get("TARGET_REPO", ""), sorta_root)

    # Parse runners_enabled
    runners_raw = env.get("RUNNERS_ENABLED", "refine,code")
    runners_enabled = [r.strip() for r in runners_raw.split(",") if r.strip()]

    # Load adapter config
    adapter_config_path = sorta_root / "adapters" / f"{adapter}.config.sh"
    statuses, transitions = load_adapter_config(adapter_config_path)

    config = Config(
        board_adapter=adapter,
        board_domain=domain,
        board_project_key=project_key,
        board_api_token=api_token,
        board_email=env.get("BOARD_EMAIL", ""),
        target_repo=target_repo,
        git_base_branch=env.get("GIT_BASE_BRANCH", "main"),
        git_release_branch=env.get("GIT_RELEASE_BRANCH", ""),
        poll_interval=int(env.get("POLL_INTERVAL", "3600")),
        runners_enabled=runners_enabled,
        max_skip_retries=int(env.get("MAX_SKIP_RETRIES", "3")),
        max_cards_refine=int(env.get("MAX_CARDS_REFINE", "5")),
        max_cards_architect=int(env.get("MAX_CARDS_ARCHITECT", "5")),
        max_cards_code=int(env.get("MAX_CARDS_CODE", "2")),
        max_cards_review=int(env.get("MAX_CARDS_REVIEW", "10")),
        max_cards_triage=int(env.get("MAX_CARDS_TRIAGE", "5")),
        max_cards_bounce=int(env.get("MAX_CARDS_BOUNCE", "10")),
        max_cards_merge=int(env.get("MAX_CARDS_MERGE", "10")),
        max_cards_documenter=int(env.get("MAX_CARDS_DOCUMENTER", "5")),
        runner_refine_from=env.get("RUNNER_REFINE_FROM", ""),
        runner_refine_to=env.get("RUNNER_REFINE_TO", ""),
        runner_refine_filter_type=env.get("RUNNER_REFINE_FILTER_TYPE", ""),
        runner_refine_agent=env.get("RUNNER_REFINE_AGENT", ""),
        runner_architect_from=env.get("RUNNER_ARCHITECT_FROM", ""),
        runner_architect_to=env.get("RUNNER_ARCHITECT_TO", ""),
        runner_architect_agent=env.get("RUNNER_ARCHITECT_AGENT", ""),
        runner_code_from=env.get("RUNNER_CODE_FROM", ""),
        runner_code_to=env.get("RUNNER_CODE_TO", ""),
        runner_code_agent=env.get("RUNNER_CODE_AGENT", ""),
        runner_review_from=env.get("RUNNER_REVIEW_FROM", ""),
        runner_review_to=env.get("RUNNER_REVIEW_TO", ""),
        runner_review_to_rejected=env.get("RUNNER_REVIEW_TO_REJECTED", ""),
        runner_review_agent=env.get("RUNNER_REVIEW_AGENT", ""),
        runner_triage_from=env.get("RUNNER_TRIAGE_FROM", ""),
        runner_triage_to=env.get("RUNNER_TRIAGE_TO", ""),
        runner_triage_filter_type=env.get("RUNNER_TRIAGE_FILTER_TYPE", "Bug"),
        runner_triage_agent=env.get("RUNNER_TRIAGE_AGENT", ""),
        runner_bounce_from=env.get("RUNNER_BOUNCE_FROM", ""),
        runner_bounce_to=env.get("RUNNER_BOUNCE_TO", ""),
        max_bounces=int(env.get("MAX_BOUNCES", "3")),
        runner_bounce_escalate=env.get("RUNNER_BOUNCE_ESCALATE", ""),
        runner_merge_from=env.get("RUNNER_MERGE_FROM", ""),
        runner_merge_to=env.get("RUNNER_MERGE_TO", ""),
        merge_strategy=env.get("MERGE_STRATEGY", "merge"),
        runner_documenter_from=env.get("RUNNER_DOCUMENTER_FROM", ""),
        runner_documenter_to=env.get("RUNNER_DOCUMENTER_TO", ""),
        docs_dir=env.get("DOCS_DIR", "docs"),
        docs_organize_by=env.get("DOCS_ORGANIZE_BY", "feature"),
        runner_documenter_agent=env.get("RUNNER_DOCUMENTER_AGENT", ""),
        runner_release_notes_agent=env.get("RUNNER_RELEASE_NOTES_AGENT", ""),
        review_max_diff_chars=int(env.get("REVIEW_MAX_DIFF_CHARS", "100000")),
        claude_agent=env.get("CLAUDE_AGENT", ""),
        gh_app_id=env.get("GH_APP_ID", ""),
        gh_app_installation_id=env.get("GH_APP_INSTALLATION_ID", ""),
        gh_app_private_key_path=env.get("GH_APP_PRIVATE_KEY_PATH", ""),
        event_logging=env.get("EVENT_LOGGING", "on"),
        adapter_statuses=statuses,
        adapter_transitions=transitions,
        sorta_root=str(sorta_root),
    )

    return config
