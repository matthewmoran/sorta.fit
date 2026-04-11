"""Sorta.Fit triage runner -- analyzes bug reports and appends root-cause analysis.

Port of runners/triage.sh. Like refine but uses triage_filter_type and appends
"## Triage Analysis (Sorta)" to the existing description.
"""
from __future__ import annotations

from sortafit.runners.base import BaseRunner, ClaudeRateLimited
from sortafit.utils import log_error, log_info, log_step, log_warn, matches_type_filter


class TriageRunner(BaseRunner):
    name = "triage"

    def process_card(self, issue_key: str) -> str:
        # Type filter (defaults to Bug in config)
        filter_type = self.config.runner_triage_filter_type
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

        log_step(f"Triaging: {issue_key} -- {title}")

        rc, triage = self._render_and_run_claude("triage.md", {
            "CARD_KEY": issue_key,
            "CARD_TITLE": title,
            "CARD_DESCRIPTION": description,
        })

        if rc == 2:
            raise ClaudeRateLimited()
        if rc != 0:
            log_error(f"Claude failed for {issue_key}")
            return "failed"
        if not triage:
            log_warn(f"Empty triage for {issue_key}. Skipping.")
            return "failed"

        # Append triage analysis to existing description
        updated_desc = (
            f"{description}\n\n---\n"
            f"## Triage Analysis (Sorta)\n"
            f"{triage}"
        )

        self.adapter.update_description(issue_key, updated_desc)
        self.adapter.add_comment(
            issue_key,
            f"Bug triaged by Sorta.Fit on {self._timestamp()}.",
        )

        self._transition(issue_key, "triaged")
        return "success"
