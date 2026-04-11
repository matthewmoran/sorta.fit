"""Loads adapter .config.sh files (STATUS_* and TRANSITION_TO_* mappings)."""
from pathlib import Path


def load_adapter_config(config_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Parse an adapter .config.sh file.

    Returns (statuses, transitions) where:
        statuses = {"STATUS_10000": "To Do", ...}
        transitions = {"TRANSITION_TO_10070": "42", ...}
    """
    statuses: dict[str, str] = {}
    transitions: dict[str, str] = {}
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
