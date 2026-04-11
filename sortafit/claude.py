"""Sorta.Fit Claude CLI wrapper -- port of run_claude() from core/utils.sh"""
from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sortafit.utils import log_error, log_info, log_warn

# Last parsed rate limit reset epoch — read by base runner to set the rate file
_last_rate_limit_reset: int | None = None


def get_rate_limit_reset() -> int | None:
    """Return the parsed reset epoch from the last rate-limited Claude run."""
    return _last_rate_limit_reset


def parse_rate_limit_reset(text: str) -> int | None:
    """Parse reset time from Claude CLI rate limit message.

    Expected format: "resets 1pm (America/Los_Angeles)" or "resets 1:30pm (UTC)"
    Returns a Unix epoch, or None if unparseable.
    """
    match = re.search(
        r"resets\s+(\d{1,2}(?::\d{2})?\s*[ap]m)\s*\(([^)]+)\)",
        text, re.IGNORECASE,
    )
    if not match:
        return None

    time_str = match.group(1).strip()
    tz_str = match.group(2).strip()

    # Resolve timezone: try zoneinfo (needs tzdata on Windows), fall back to local
    tz = None
    if tz_str.upper() == "UTC":
        tz = timezone.utc
    else:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_str)
        except Exception:
            pass  # fall back to local time

    now = datetime.now(tz)

    # Parse "1pm", "1:30pm", "12am" etc. manually (strptime is too picky)
    tm = re.match(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", time_str, re.IGNORECASE)
    if not tm:
        return None
    hour = int(tm.group(1))
    minute = int(tm.group(2) or "0")
    ampm = tm.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    reset_dt = now.replace(
        hour=hour, minute=minute, second=0, microsecond=0,
    )

    # If the reset time appears to be in the past, it means tomorrow
    if reset_dt <= now:
        reset_dt += timedelta(days=1)

    return int(reset_dt.timestamp())


def run_claude(
    prompt_file: Path,
    result_file: Path,
    work_dir: str = "",
    agent: str = "",
) -> int:
    """Run Claude Code CLI and extract the result.

    Port of bash run_claude(). Shells out to `claude -p --verbose --output-format stream-json`,
    parses the JSON stream, logs tool activity, and writes the result to result_file.

    Returns:
        0 on success, 1 on failure, 2 on rate limit.
    """
    cmd = ["claude", "-p", "--verbose", "--output-format", "stream-json"]
    if agent:
        cmd.extend(["--agent", agent])

    cwd = work_dir or None

    try:
        with open(prompt_file, "r", encoding="utf-8") as stdin_file:
            proc = subprocess.Popen(
                cmd,
                stdin=stdin_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                text=True,
                encoding="utf-8",
            )
    except FileNotFoundError:
        log_error("'claude' command not found")
        return 1

    result_text = ""
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Extract result
            if event.get("type") == "result":
                result_text = event.get("result", "")

            # Log tool activity (matching the Node.js stream parser)
            if event.get("type") == "assistant":
                for content in event.get("message", {}).get("content", []):
                    if content.get("type") == "tool_use":
                        _log_tool_use(content)
                    elif content.get("type") == "text" and content.get("text"):
                        first_line = content["text"].split("\n")[0].strip()
                        if first_line:
                            log_info(f"  [CLAUDE] {first_line[:120]}")
    except Exception:
        pass

    proc.wait()

    # Read stderr
    stderr_content = ""
    try:
        stderr_content = proc.stderr.read()
    except Exception:
        pass

    if proc.returncode != 0:
        if stderr_content:
            log_error(f"Claude stderr: {stderr_content[:300]}")

        if re.search(
            r"rate.limit|too.many.requests|usage.limit|capacity|throttl|hit your limit",
            stderr_content,
            re.IGNORECASE,
        ):
            global _last_rate_limit_reset
            _last_rate_limit_reset = parse_rate_limit_reset(stderr_content)
            log_warn("Claude rate limit detected. Pausing further runs.")
            return 2

        return 1

    # Log stderr warnings even on success
    if stderr_content:
        log_warn(f"Claude stderr: {stderr_content[:200]}")

    # Write result
    result_file.write_text(result_text, encoding="utf-8")
    return 0


def _log_tool_use(content: dict) -> None:
    """Log a Claude tool use event (matching Node.js activity logger)."""
    name = content.get("name", "")
    inp = content.get("input", {})
    detail = inp.get("file_path", "") or inp.get("pattern", "")
    if name == "Bash":
        detail = (inp.get("command", ""))[:80]
    elif name == "Edit":
        detail = inp.get("file_path", "") + (" (modify)" if inp.get("old_string") else "")
    elif name == "Write":
        detail = inp.get("file_path", "") + " (create)"
    log_info(f"  [CLAUDE] {name}" + (f": {detail}" if detail else ""))
