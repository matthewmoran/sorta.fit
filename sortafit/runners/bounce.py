"""Sorta.Fit bounce runner -- moves rejected PRs back for rework.

Port of runners/bounce.sh. Extracts PR URL -> checks if PR has CHANGES_REQUESTED ->
counts bounces -> if >= MAX_BOUNCES escalate -> else transition back to code lane.
"""
from __future__ import annotations

import json
import re
import subprocess

from sortafit.events import log_event
from sortafit.runners.base import BaseRunner
from sortafit.runner_lib import check_pr_review_state, runner_transition
from sortafit.utils import extract_pr_url, find_gh, log_info, log_step, log_warn


class BounceRunner(BaseRunner):
    name = "bounce"

    def __init__(self, config, adapter) -> None:
        super().__init__(config, adapter)
        self._gh = find_gh()
        self._max_bounces = config.max_bounces
        self._escalate_to = config.runner_bounce_escalate

    def process_card(self, issue_key: str) -> str:
        try:
            title = self.adapter.get_card_title(issue_key)
        except Exception:
            log_warn(f"Failed to fetch title for {issue_key}. Skipping.")
            return "skipped"

        try:
            comments = self.adapter.get_card_comments(issue_key)
        except Exception:
            log_warn(f"Failed to fetch comments for {issue_key}. Skipping.")
            return "skipped"

        # Find most recent PR URL in comments
        pr_url = extract_pr_url(comments)
        if not pr_url:
            log_info(f"No PR URL for {issue_key}. Skipping.")
            return "skipped"

        # Count previous bounces
        bounce_count = len(re.findall(r"Bounced by Sorta", comments))

        # If already at max bounces, escalate
        if bounce_count >= self._max_bounces:
            # Only escalate once
            if "Escalated by Sorta" in comments:
                log_info(f"{issue_key} already escalated. Skipping.")
                return "skipped"

            log_warn(
                f"{issue_key} has bounced {bounce_count} times "
                f"(max: {self._max_bounces}). Escalating for human review."
            )
            self.adapter.add_comment(
                issue_key,
                f"Escalated by Sorta.Fit on {self._timestamp()}. "
                f"This card has been bounced {bounce_count} times and needs human attention. "
                f"PR: {pr_url}",
            )
            log_event(
                "bounce_escalated", self.config,
                runner_name=self.name,
                card_key=issue_key,
                bounce_count=str(bounce_count),
                max_bounces=str(self._max_bounces),
            )

            if self._escalate_to:
                runner_transition(
                    issue_key, self._escalate_to, "escalated",
                    self.config, self.adapter,
                )

            return "success"

        # Skip if rework already pushed after last review (needs re-review, not bounce)
        # Primary check: compare last reviewed commit against PR HEAD
        if self._has_commits_after_last_review(pr_url):
            log_info(
                f"{issue_key}: new commits pushed after last review. "
                f"Needs re-review, not bounce."
            )
            return "skipped"

        # Fallback: check card comments for rework-after-review pattern
        lines = comments.splitlines()
        last_review_line = 0
        last_rework_line = 0
        for i, line in enumerate(lines, 1):
            if "Code Review \u2014" in line or "Code Review --" in line:
                last_review_line = i
            if "Rework pushed by Sorta" in line:
                last_rework_line = i

        if last_review_line and last_rework_line and last_rework_line > last_review_line:
            log_info(
                f"{issue_key}: rework already pushed after last review. "
                f"Needs re-review, not bounce."
            )
            return "skipped"

        # Check the PR review state
        should_bounce = False
        review_comments = ""

        if check_pr_review_state(pr_url, "CHANGES_REQUESTED"):
            should_bounce = True
            # Get review comments
            try:
                result = subprocess.run(
                    [self._gh, "pr", "view", pr_url, "--json", "reviews",
                     "--jq", "[.reviews[] | select(.state == \"CHANGES_REQUESTED\") | .body] | last"],
                    capture_output=True, text=True, encoding="utf-8", timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    review_comments = result.stdout.strip()
            except Exception:
                pass
        else:
            # Fallback: check card comments for Sorta.Fit review verdict
            # This covers when the bot can't post a formal GitHub review
            # (e.g., can't review your own PR) and falls back to a comment
            last_review = ""
            for line in lines:
                if "Code Review \u2014" in line or "Code Review --" in line:
                    last_review = line
            if last_review and re.search(
                r"Changes Requested|\bCritical\b|\bWarning\b",
                last_review, re.IGNORECASE,
            ):
                should_bounce = True
                review_comments = last_review

        if not should_bounce:
            log_info(f"{issue_key}: PR not rejected. Skipping.")
            return "skipped"

        log_step(
            f"Bouncing: {issue_key} -- {title} "
            f"(attempt {bounce_count + 1}/{self._max_bounces})"
        )

        bounce_msg = (
            f"Bounced by Sorta.Fit on {self._timestamp()} "
            f"(attempt {bounce_count + 1}/{self._max_bounces}). "
            f"PR review requested changes."
        )
        if review_comments and review_comments != "null":
            bounce_msg += f"\n\nReview feedback:\n{review_comments}"

        self.adapter.add_comment(issue_key, bounce_msg)
        log_event(
            "bounce_triggered", self.config,
            runner_name=self.name,
            card_key=issue_key,
            bounce_count=str(bounce_count + 1),
        )

        self._transition(issue_key, "bounced")
        return "success"

    def _has_commits_after_last_review(self, pr_url: str) -> bool:
        """Check if the PR has commits pushed after the last CHANGES_REQUESTED review."""
        try:
            result = subprocess.run(
                [self._gh, "pr", "view", pr_url,
                 "--json", "reviews,commits"],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            if result.returncode != 0:
                return False
            data = json.loads(result.stdout)
        except Exception:
            return False

        reviews = data.get("reviews", [])
        commits = data.get("commits", [])
        if not reviews or not commits:
            return False

        # Find the commit OID from the last CHANGES_REQUESTED review
        last_cr_oid = ""
        for review in reviews:
            if review.get("state") == "CHANGES_REQUESTED":
                last_cr_oid = (review.get("commit") or {}).get("oid", "")

        if not last_cr_oid:
            return False

        latest_oid = commits[-1].get("oid", "")
        return bool(latest_oid and latest_oid != last_cr_oid)
