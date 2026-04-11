"""Sorta.Fit release notes generator -- standalone, NOT loop-based.

Port of runners/release-notes.sh. Called directly with arguments, not as a runner.
Gets commit log since a tag/date/SHA, renders a prompt, runs Claude, outputs
release notes to stdout and optionally to a file.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from sortafit.claude import run_claude
from sortafit.config import Config
from sortafit.utils import log_error, log_info, log_warn


def release_notes(since: str, output_file: str = "", config: Config | None = None) -> str:
    """Generate release notes from commits since a tag, date, or SHA.

    Args:
        since: Git tag, date (YYYY-MM-DD), or commit SHA.
        output_file: Optional path to write the release notes to.
        config: Config instance. Required for TARGET_REPO and agent.

    Returns:
        The generated release notes text, or empty string on failure.
    """
    if not since:
        raise ValueError("Usage: release_notes(since, [output_file], [config])\n"
                         "  since: git tag, date (YYYY-MM-DD), or commit SHA")

    if config is None:
        from sortafit.config import load_config
        config = load_config()

    target_repo = config.target_repo
    agent = config.runner_release_notes_agent or config.claude_agent

    log_info(f"Generating release notes since: {since}")

    # Get commit log
    try:
        result = subprocess.run(
            ["git", "-C", target_repo, "log",
             f"{since}..HEAD", "--pretty=format:%H|%s", "--no-merges"],
            capture_output=True, text=True, encoding="utf-8",
        )
        git_log = result.stdout.strip()
    except Exception:
        git_log = ""

    if not git_log:
        log_warn(f"No commits found since {since}")
        return ""

    # Build commit list for the prompt
    commit_list = ""
    for line in git_log.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 1)
        if len(parts) < 2:
            continue
        sha, subject = parts
        commit_list += f"\n- {sha[:8]}: {subject}"

    prompt = (
        f"Generate user-friendly release notes from these commits. "
        f"Group into: New Features, Improvements, Bug Fixes, Breaking Changes. "
        f"Omit empty sections. Write for end users, not developers. Be concise.\n\n"
        f"## Commits since {since}\n"
        f"{commit_list}\n\n"
        f"Output the release notes in markdown format."
    )

    prompt_file = Path(tempfile.mktemp(suffix=".prompt.md"))
    result_file = Path(tempfile.mktemp(suffix=".result.md"))

    try:
        prompt_file.write_text(prompt, encoding="utf-8")

        rc = run_claude(prompt_file, result_file, "", agent)

        if rc != 0:
            log_error("Claude failed to generate release notes")
            return ""

        notes = result_file.read_text(encoding="utf-8") if result_file.exists() else ""
    finally:
        prompt_file.unlink(missing_ok=True)
        result_file.unlink(missing_ok=True)

    if notes:
        print(notes)

        if output_file:
            Path(output_file).write_text(notes, encoding="utf-8")
            log_info(f"Written to {output_file}")

    return notes
