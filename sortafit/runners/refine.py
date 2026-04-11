"""Sorta.Fit refine runner -- generates structured specs from raw cards.

Port of runners/refine.sh. Simplest runner: fetch card -> optional type filter ->
render refine.md -> run Claude -> update description -> add comment -> transition.
"""
from __future__ import annotations

from sortafit.config import Config
from sortafit.events import log_event
from sortafit.runners.base import BaseRunner, ClaudeRateLimited
from sortafit.utils import log_error, log_info, log_step, log_warn, matches_type_filter


class RefineRunner(BaseRunner):
    name = "refine"

    def process_card(self, issue_key: str) -> str:
        # Type filter
        filter_type = self.config.runner_refine_filter_type
        if filter_type:
            try:
                card_type = self.adapter.get_card_type(issue_key)
            except Exception:
                log_warn(f"Failed to fetch type for {issue_key}. Skipping.")
                return "skipped"
            if not matches_type_filter(card_type, filter_type):
                log_info(f"Skipping {issue_key} (type: {card_type}, filter: {filter_type})")
                return "skipped"

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

        log_step(f"Refining: {issue_key} -- {title}")

        rc, result = self._render_and_run_claude("refine.md", {
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
        if not result:
            log_error(f"Empty response for {issue_key}, skipping")
            return "failed"

        self.adapter.update_description(issue_key, result)
        self.adapter.add_comment(
            issue_key,
            f"Card refined by Sorta.Fit on {self._timestamp()}. "
            f"Review and move to Agent lane when ready.",
        )

        self._transition(issue_key, "refined")
        return "success"
