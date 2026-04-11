"""Sorta.Fit utilities -- port of core/utils.sh"""
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


# --- Logging ---
# Colors disabled if not a terminal (matching bash: if [[ -t 1 ]])

def _use_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"


def log_info(msg: str) -> None:
    """Print info message to stdout (green [INFO] prefix)."""
    if _use_color():
        print(f"{GREEN}[INFO]{NC} {msg}")
    else:
        print(f"[INFO] {msg}")


def log_warn(msg: str) -> None:
    """Print warning to stderr (yellow [WARN] prefix)."""
    if _use_color():
        print(f"{YELLOW}[WARN]{NC} {msg}", file=sys.stderr)
    else:
        print(f"[WARN] {msg}", file=sys.stderr)


def log_error(msg: str) -> None:
    """Print error to stderr (red [ERROR] prefix)."""
    if _use_color():
        print(f"{RED}[ERROR]{NC} {msg}", file=sys.stderr)
    else:
        print(f"[ERROR] {msg}", file=sys.stderr)


def log_step(msg: str) -> None:
    """Print step message to stdout (blue [STEP] prefix)."""
    if _use_color():
        print(f"{BLUE}[STEP]{NC} {msg}")
    else:
        print(f"[STEP] {msg}")


# --- Text Processing ---

def slugify(text: str, max_len: int = 40) -> str:
    """Convert text to branch-safe slug. Port of bash slugify().

    Lowercase, replace non-alphanumeric with hyphens, collapse consecutive hyphens,
    strip leading/trailing hyphens, truncate to max_len.
    """
    result = text.lower()
    result = re.sub(r"[^a-z0-9]", "-", result)
    result = re.sub(r"-+", "-", result)
    result = result.strip("-")
    return result[:max_len]


def render_template(template_path: Path, **kwargs: str) -> str:
    """Render a prompt template by replacing {{KEY}} placeholders.

    Port of bash render_template() -- but pure Python instead of Node.js.
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    content = template_path.read_text(encoding="utf-8")
    for key, value in kwargs.items():
        content = content.replace("{{" + key + "}}", value)
    return content


def matches_type_filter(card_type: str, filter_str: str) -> bool:
    """Check if a card type matches a comma-separated filter.

    Returns True if filter is empty (no filter = match all) or card_type is in the filter.
    Port of bash matches_type_filter().
    """
    if not filter_str:
        return True
    types = [t.strip() for t in filter_str.split(",")]
    return card_type in types


def extract_pr_url(text: str, last: bool = True) -> str:
    """Extract a GitHub PR URL from text.

    Args:
        text: Text to search.
        last: If True, return last match (utils.sh behavior).
              If False, return first match (runner-lib.sh behavior).
    """
    matches = re.findall(r"https://github\.com/[^/]+/[^/]+/pull/[0-9]+", text)
    if not matches:
        return ""
    return matches[-1] if last else matches[0]


# --- Lock Management ---

def lock_acquire(lock_dir: Path) -> bool:
    """Acquire an atomic directory-based lock. Port of bash lock_acquire().

    Uses mkdir for atomicity. Checks if holder PID is still alive for stale lock cleanup.
    """
    try:
        lock_dir.mkdir()
        (lock_dir / "pid").write_text(str(os.getpid()))
        return True
    except FileExistsError:
        pass

    # Lock exists -- check if holder is still alive
    pid_file = lock_dir / "pid"
    try:
        lock_pid = int(pid_file.read_text().strip())
    except (FileNotFoundError, ValueError):
        lock_pid = 0

    if lock_pid:
        try:
            os.kill(lock_pid, 0)  # Check if process exists
            log_warn(f"Previous cycle (PID {lock_pid}) still running. Skipping.")
            return False
        except OSError:
            pass  # Process doesn't exist -- stale lock

    # Stale lock -- remove and retry
    log_warn(f"Stale lock (PID {lock_pid}). Removing.")
    import shutil as _shutil
    _shutil.rmtree(lock_dir, ignore_errors=True)
    try:
        lock_dir.mkdir()
        (lock_dir / "pid").write_text(str(os.getpid()))
        return True
    except FileExistsError:
        return False


def lock_release(lock_dir: Path) -> None:
    """Release a directory-based lock. Port of bash lock_release()."""
    import shutil as _shutil
    _shutil.rmtree(lock_dir, ignore_errors=True)


# --- Rate Limiting ---

def is_rate_limited(sorta_root: str) -> bool:
    """Check if we're currently rate limited.

    The .rate-limited file stores the Unix epoch when the limit resets.
    """
    rate_file = Path(sorta_root) / ".rate-limited"
    if not rate_file.exists():
        return False

    try:
        reset_epoch = int(rate_file.read_text().strip())
    except (ValueError, FileNotFoundError):
        return False

    now = int(time.time())
    if now < reset_epoch:
        remaining = reset_epoch - now
        log_warn(f"Rate limited. {remaining}s remaining before retry.")
        return True

    # Reset time has passed -- clear the flag
    rate_file.unlink(missing_ok=True)
    return False


def get_rate_limit_reset_epoch(sorta_root: str) -> int | None:
    """Read the reset epoch from the rate limit file, or None if not limited."""
    rate_file = Path(sorta_root) / ".rate-limited"
    if not rate_file.exists():
        return None
    try:
        return int(rate_file.read_text().strip())
    except (ValueError, FileNotFoundError):
        return None


def set_rate_limited(sorta_root: str, reset_epoch: int | None = None) -> None:
    """Set the rate limit flag with the epoch when the limit resets.

    If reset_epoch is None, defaults to 30 minutes from now.
    """
    if reset_epoch is None:
        reset_epoch = int(time.time()) + 1800
    rate_file = Path(sorta_root) / ".rate-limited"
    rate_file.write_text(str(reset_epoch))


# --- Dependency Checking ---

def require_command(cmd: str, install_hint: str = "") -> bool:
    """Check if a command exists. Port of bash require_command()."""
    if shutil.which(cmd):
        return True
    # Windows fallback for gh
    if cmd == "gh":
        gh_path = Path("/c/Program Files/GitHub CLI/gh.exe")
        if gh_path.exists():
            return True
    log_error(f"'{cmd}' is not installed.")
    if install_hint:
        print(f"  Install: {install_hint}", file=sys.stderr)
    return False


def find_gh() -> str:
    """Find the gh CLI command. Port of bash find_gh()."""
    if shutil.which("gh"):
        return "gh"
    gh_path = "/c/Program Files/GitHub CLI/gh.exe"
    if Path(gh_path).exists():
        return gh_path
    return "gh"


def preflight_check() -> bool:
    """Verify all dependencies. Port of bash preflight_check()."""
    log_step("Checking dependencies...")
    failed = False

    if not require_command("claude", "https://claude.ai/code"):
        failed = True
    if not require_command("git", "https://git-scm.com/downloads"):
        failed = True

    gh_cmd = find_gh()
    result = subprocess.run(
        [gh_cmd, "--version"], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        log_error("'gh' (GitHub CLI) is not installed.")
        print("  Install: https://cli.github.com", file=sys.stderr)
        failed = True

    if failed:
        log_error("Missing dependencies. Install them and try again.")
        return False

    log_info("All dependencies found.")
    return True
