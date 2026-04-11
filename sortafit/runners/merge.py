"""Sorta.Fit merge runner -- merges approved PRs and transitions cards to Done.

Port of runners/merge.sh. Extracts PR URL -> checks APPROVED state ->
merges via gh pr merge -> optional promotion PR to release branch.
"""
from __future__ import annotations

import subprocess

from sortafit.events import log_event
from sortafit.runners.base import BaseRunner
from sortafit.runner_lib import check_pr_review_state
from sortafit.utils import extract_pr_url, find_gh, log_error, log_info, log_step, log_warn


class MergeRunner(BaseRunner):
    name = "merge"

    def __init__(self, config, adapter) -> None:
        super().__init__(config, adapter)
        self._gh = find_gh()

        # Validate merge strategy
        if config.merge_strategy not in ("merge", "squash", "rebase"):
            raise ValueError(
                f"Invalid MERGE_STRATEGY: {config.merge_strategy} "
                f"(must be merge, squash, or rebase)"
            )

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
            log_info(f"{issue_key}: no PR URL in comments. Skipping.")
            return "skipped"

        # Check PR review decision
        if not check_pr_review_state(pr_url, "APPROVED"):
            log_info(f"{issue_key}: PR not approved. Skipping.")
            return "skipped"

        strategy = self.config.merge_strategy
        log_step(f"Merging: {issue_key} -- {title} (--{strategy})")

        # Merge the PR
        try:
            result = subprocess.run(
                [self._gh, "pr", "merge", pr_url, f"--{strategy}"],
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            if result.returncode != 0:
                merge_output = result.stdout + result.stderr
                log_error(f"Merge failed for {issue_key}: {merge_output}")
                self.adapter.add_comment(
                    issue_key,
                    f"Sorta.Fit merge failed on {self._timestamp()}. "
                    f"PR: {pr_url}. Error: {merge_output}",
                )
                return "failed"
        except Exception as exc:
            log_error(f"Merge failed for {issue_key}: {exc}")
            return "failed"

        log_event(
            "pr_merged", self.config,
            runner_name=self.name,
            card_key=issue_key,
            pr_url=pr_url,
            merge_strategy=strategy,
        )
        self.adapter.add_comment(
            issue_key,
            f"Merged by Sorta.Fit on {self._timestamp()}. PR: {pr_url} ({strategy})",
        )

        self._transition(issue_key, "merged")

        # Promotion PR: if GIT_RELEASE_BRANCH is set and differs from GIT_BASE_BRANCH
        self._create_promotion_pr()

        return "success"

    def _create_promotion_pr(self) -> None:
        """Create a promotion PR from base -> release branch if configured."""
        release = self.config.git_release_branch
        base = self.config.git_base_branch

        if not release or release == base:
            return

        # Check for existing promotion PR
        try:
            result = subprocess.run(
                [self._gh, "pr", "list",
                 "--base", release, "--head", base,
                 "--json", "number", "--jq", ".[0].number"],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            existing = result.stdout.strip()
            if existing and existing != "null":
                return  # Already exists
        except Exception:
            pass

        log_step(f"Opening promotion PR: {base} -> {release}")

        try:
            result = subprocess.run(
                [self._gh, "pr", "create",
                 "--base", release, "--head", base,
                 f"--title", f"Promote {base} -> {release}",
                 "--body", f"Automated promotion PR created by Sorta.Fit on {self._timestamp()}."],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                log_info(f"Promotion PR opened: {result.stdout.strip()}")
            else:
                log_warn(f"Failed to create promotion PR: {result.stderr}")
        except Exception as exc:
            log_warn(f"Failed to create promotion PR: {exc}")

