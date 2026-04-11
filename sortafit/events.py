"""Sorta.Fit event logger — port of log_event() from core/utils.sh"""
import json
from datetime import datetime, timezone
from pathlib import Path

from sortafit.config import Config


def log_event(
    event_type: str,
    config: Config,
    runner_name: str = "",
    cycle_id: str = "",
    **data: str,
) -> None:
    """Append a structured JSON event to .sorta/events.jsonl.

    Non-blocking, failure-tolerant (matches bash behavior).
    """
    try:
        if config.event_logging != "on":
            return

        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event_type,
            "runner": runner_name or "unknown",
        }
        if cycle_id:
            entry["cycle_id"] = cycle_id
        if data:
            entry["data"] = {k: str(v) for k, v in data.items()}

        event_dir = Path(config.sorta_root) / ".sorta"
        event_dir.mkdir(parents=True, exist_ok=True)
        with open(event_dir / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # failure-tolerant, matching bash behavior
