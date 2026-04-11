"""Sorta.Fit architect runner -- enriches refined specs with implementation plans.

Port of runners/architect.sh. Nearly identical to refine but appends
"## Architecture Plan (Sorta)" to the existing description instead of replacing it.
"""
from __future__ import annotations

from sortafit.runners.base import BaseRunner, ClaudeRateLimited
from sortafit.utils import log_error, log_info, log_step, log_warn


class ArchitectRunner(BaseRunner):
    name = "architect"

    def process_card(self, issue_key: str) -> str:
        try:
            title = self.adapter.get_card_title(issue_key)
        except Exception:
            log_warn(f"Failed to fetch title for {issue_key}. Skipping.")
            return "skipped"

        try:
            description = self.adapter.get_card_description(issue_key)
        except Exception:
            log_warn(f"Failed to fetch description for {issue_key}. Skipping.")
            return "skipped"

        try:
            comments = self.adapter.get_card_comments(issue_key)
        except Exception:
            log_warn(f"Failed to fetch comments for {issue_key}. Skipping.")
            return "skipped"

        log_step(f"Architecting: {issue_key} -- {title}")

        rc, arch_plan = self._render_and_run_claude("architect.md", {
            "CARD_KEY": issue_key,
            "CARD_TITLE": title,
            "CARD_DESCRIPTION": description,
            "CARD_COMMENTS": comments,
        })

        if rc == 2:
            raise ClaudeRateLimited()
        if rc != 0:
            log_error(f"Claude failed for {issue_key}, skipping")
            return "failed"
        if not arch_plan:
            log_warn(f"Empty architecture plan for {issue_key}. Skipping.")
            return "failed"

        # Append architecture plan to existing description
        updated_desc = (
            f"{description}\n\n---\n"
            f"## Architecture Plan (Sorta)\n"
            f"{arch_plan}"
        )

        self.adapter.update_description(issue_key, updated_desc)
        self.adapter.add_comment(
            issue_key,
            f"Card architected by Sorta.Fit on {self._timestamp()}. Ready for implementation.",
        )

        self._transition(issue_key, "architected")
        return "success"
