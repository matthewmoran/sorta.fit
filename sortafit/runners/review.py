"""Sorta.Fit review runner -- reviews PR diffs and posts feedback to GitHub.

Port of runners/review.sh. Extracts PR URL from card comments -> gets diff via
gh pr diff -> filters noise files -> smart-truncates by whole files -> renders
review.md -> runs Claude -> parses VERDICT line -> posts review to GitHub ->
posts to card comments -> transitions.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from fnmatch import fnmatch
from pathlib import Path

from sortafit.runners.base import BaseRunner, ClaudeRateLimited
from sortafit.utils import (
    extract_pr_url,
    find_gh,
    log_error,
    log_info,
    log_step,
    log_warn,
)

# Files that add noise to reviews -- lock files, minified assets, source maps, snapshots
NOISE_PATTERNS = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Pipfile.lock",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
]


def parse_diff_files(raw_diff: str) -> list[tuple[str, str]]:
    """Split a unified diff into per-file chunks.

    Returns a list of (filename, chunk) tuples.
    """
    if not raw_diff.strip():
        return []

    chunks: list[tuple[str, str]] = []
    # Split on diff boundaries, keeping the delimiter
    parts = re.split(r"(?=^diff --git )", raw_diff, flags=re.MULTILINE)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Extract filename from "diff --git a/path b/path"
        match = re.match(r"diff --git a/(.+?) b/(.+)", part)
        if match:
            filename = match.group(2)
            # Restore trailing newline for clean concatenation
            chunks.append((filename, part + "\n"))

    return chunks


def _is_noise(filename: str) -> bool:
    """Check if a filename matches any noise pattern."""
    basename = filename.rsplit("/", 1)[-1] if "/" in filename else filename
    return any(fnmatch(basename, pat) for pat in NOISE_PATTERNS)


def prepare_diff(raw_diff: str, max_chars: int) -> str:
    """Filter noise files and smart-truncate a diff by whole files.

    1. Parse the diff into per-file chunks.
    2. Remove noise files (lock files, minified assets, etc.).
    3. If remaining files exceed max_chars, drop whole files from the end.
    4. Append a summary of anything that was filtered or dropped.
    """
    file_chunks = parse_diff_files(raw_diff)
    if not file_chunks:
        return raw_diff

    # Separate signal from noise
    signal: list[tuple[str, str]] = []
    noise_names: list[str] = []
    for filename, chunk in file_chunks:
        if _is_noise(filename):
            noise_names.append(filename)
        else:
            signal.append((filename, chunk))

    if not signal:
        names = ", ".join(noise_names)
        return f"[No reviewable files — all {len(noise_names)} files filtered out as noise: {names}]"

    # Build diff from signal files, dropping from the end if over limit
    # Reserve space for a potential summary footer
    summary_reserve = 200
    budget = max_chars - summary_reserve
    if budget < 0:
        budget = max_chars

    included: list[str] = []
    included_size = 0
    dropped_names: list[str] = []

    for filename, chunk in signal:
        if included_size + len(chunk) <= budget:
            included.append(chunk)
            included_size += len(chunk)
        else:
            # If this is the first file and it alone exceeds the budget,
            # include a truncated version rather than showing nothing
            if not included:
                truncated = chunk[:budget]
                # Try to cut at the last complete line
                last_newline = truncated.rfind("\n")
                if last_newline > 0:
                    truncated = truncated[:last_newline + 1]
                included.append(truncated)
                included_size += len(truncated)
                dropped_names.append(f"{filename} (truncated)")
            else:
                dropped_names.append(filename)

    result = "".join(included)

    # Build summary footer
    notes: list[str] = []
    if noise_names:
        names = ", ".join(noise_names)
        notes.append(f"Filtered out {len(noise_names)} noise file(s): {names}")
    if dropped_names:
        names = ", ".join(dropped_names)
        notes.append(f"Omitted {len(dropped_names)} file(s) to fit size limit: {names}")

    if notes:
        footer = "\n\n--- diff summary ---\n" + "\n".join(notes) + "\n"
        result += footer

    return result


class ReviewRunner(BaseRunner):
    name = "review"

    def __init__(self, config, adapter) -> None:
        super().__init__(config, adapter)
        self._gh = find_gh()

    def _gh_review_env(self) -> dict[str, str] | None:
        """Return env dict with bot token for gh review calls, or None for default auth."""
        if self.config.gh_app_token:
            env = os.environ.copy()
            env["GH_TOKEN"] = self.config.gh_app_token
            return env
        return None

    def process_card(self, issue_key: str) -> str:
        try:
            comments = self.adapter.get_card_comments(issue_key)
        except Exception:
            log_warn(f"Failed to fetch comments for {issue_key}. Skipping.")
            return "skipped"

        # Find most recent PR URL in comments
        pr_url = extract_pr_url(comments)
        if not pr_url:
            log_info(f"No PR URL found for {issue_key}. Skipping.")
            return "skipped"

        # Check if already reviewed by Sorta.Fit (allow re-review after rework)
        if "Code Review \u2014" in comments or "Code Review --" in comments:
            review_pattern = r"Code Review [—\-]+"
            rework_pattern = r"Rework pushed by Sorta\.Fit"

            # Find line numbers of last review and last rework
            lines = comments.splitlines()
            last_review_line = 0
            last_rework_line = 0
            for i, line in enumerate(lines, 1):
                if re.search(review_pattern, line):
                    last_review_line = i
                if re.search(rework_pattern, line):
                    last_rework_line = i

            if last_review_line > 0:
                if last_rework_line == 0 or last_review_line > last_rework_line:
                    log_info(f"{issue_key} already reviewed. Skipping.")
                    return "skipped"
                log_info(f"{issue_key} has rework after last review. Re-reviewing.")

        log_step(f"Reviewing: {issue_key} -- {pr_url}")

        # Get PR diff
        try:
            result = subprocess.run(
                [self._gh, "pr", "diff", pr_url],
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            pr_diff = result.stdout
            if result.returncode != 0:
                log_error(f"Failed to get diff for {pr_url}")
                return "skipped"
        except Exception as exc:
            log_error(f"Failed to get diff for {pr_url}: {exc}")
            return "skipped"

        if not pr_diff:
            log_warn(f"Empty diff for {pr_url}. Skipping.")
            return "skipped"

        # Filter noise and smart-truncate large diffs
        max_chars = self.config.review_max_diff_chars
        raw_len = len(pr_diff)
        pr_diff = prepare_diff(pr_diff, max_chars)
        if raw_len != len(pr_diff):
            log_info(f"Diff prepared: {raw_len} -> {len(pr_diff)} chars (limit {max_chars})")

        # Run Claude for review
        rc, review = self._render_and_run_claude("review.md", {
            "CARD_KEY": issue_key,
            "PR_URL": pr_url,
            "PR_DIFF": pr_diff,
        })

        if rc == 2:
            raise ClaudeRateLimited()
        if rc != 0:
            log_error(f"Claude failed for review of {issue_key}")
            return "failed"
        if not review:
            log_warn(f"Empty review for {issue_key}. Skipping.")
            return "failed"

        # Parse verdict line from Claude's output
        review_event = "comment"
        verdict_match = re.search(r"^VERDICT: (APPROVE|REQUEST_CHANGES)", review, re.MULTILINE)
        if verdict_match:
            verdict = verdict_match.group(1)
            if verdict == "APPROVE":
                review_event = "approve"
            elif verdict == "REQUEST_CHANGES":
                review_event = "request-changes"

        # Strip verdict lines from review body before posting
        review_body = re.sub(r"^VERDICT: .*\n?", "", review, flags=re.MULTILINE)

        # Post to GitHub
        log_info(f"Posting review ({review_event}) to {pr_url}...")

        review_body_file = Path(tempfile.mktemp(suffix=".review.md"))
        try:
            review_body_file.write_text(review_body, encoding="utf-8")

            bot_env = self._gh_review_env()
            post_result = subprocess.run(
                [self._gh, "pr", "review", pr_url, f"--{review_event}", "--body-file", str(review_body_file)],
                capture_output=True, text=True, encoding="utf-8",
                env=bot_env,
            )
            if post_result.returncode != 0:
                # Can't review -- fallback to comment with verdict marker
                log_info("Review submission failed — posting as comment with verdict marker.")
                fallback_prefix = ""
                if review_event == "request-changes":
                    fallback_prefix = (
                        "**[CHANGES REQUESTED]** _(posted as comment because "
                        "the bot cannot submit a formal review on this PR)_\n\n"
                    )
                elif review_event == "approve":
                    fallback_prefix = (
                        "**[APPROVED]** _(posted as comment because "
                        "the bot cannot submit a formal review on this PR)_\n\n"
                    )
                fallback_file = Path(tempfile.mktemp(suffix=".fallback.md"))
                try:
                    fallback_file.write_text(
                        fallback_prefix + review_body, encoding="utf-8",
                    )
                    subprocess.run(
                        [self._gh, "pr", "comment", pr_url, "--body-file", str(fallback_file)],
                        capture_output=True, text=True, encoding="utf-8",
                        env=bot_env,
                    )
                finally:
                    fallback_file.unlink(missing_ok=True)
        finally:
            review_body_file.unlink(missing_ok=True)

        # Post full review to card so board watchers see everything
        verdict_label = "Comment"
        if review_event == "approve":
            verdict_label = "Approved"
        elif review_event == "request-changes":
            verdict_label = "Changes Requested"

        self.adapter.add_comment(
            issue_key,
            f"Code Review \u2014 {verdict_label} ({pr_url})\n\n{review_body}",
        )

        # Transition based on verdict — approved cards move forward, rejected stay/go back
        if review_event == "approve":
            self._transition(issue_key, "reviewed")
        else:
            rejected_status = self.config.runner_review_to_rejected
            if rejected_status:
                from sortafit.runner_lib import runner_transition
                runner_transition(issue_key, rejected_status, "review-rejected",
                                  self.config, self.adapter)
            else:
                log_info(f"{issue_key} review rejected — staying in current lane for bounce runner.")
        return "success"
