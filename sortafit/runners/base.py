"""Sorta.Fit base runner -- extracts the shared loop pattern from all bash runners."""
from __future__ import annotations

import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from sortafit.claude import get_rate_limit_reset, run_claude
from sortafit.config import Config
from sortafit.events import log_event
from sortafit.utils import log_error, log_info, log_step, log_warn, render_template, set_rate_limited


class ClaudeRateLimited(Exception):
    """Raised when Claude returns exit code 2 (rate limited)."""

    def __init__(self, reset_epoch: int | None = None):
        self.reset_epoch = reset_epoch
        super().__init__()


class BaseRunner(ABC):
    """Abstract base runner implementing the shared batch loop.

    Every bash runner follows the same pattern:
      1. Log runner_started
      2. Outer while-true with skip-retry: fetch batch -> inner loop -> skip-retry if no cards processed
      3. For each card: get key, title, description, comments -> process -> transition -> log event
      4. Log runner_completed

    Subclasses override ``process_card`` (and optionally ``fetch_card_data``)
    to implement runner-specific logic.
    """

    name: str = ""

    def __init__(self, config: Config, adapter) -> None:
        self.config = config
        self.adapter = adapter

    # -- Properties derived from config using self.name --

    @property
    def from_status(self) -> str:
        return getattr(self.config, f"runner_{self.name}_from", "")

    @property
    def to_status(self) -> str:
        return getattr(self.config, f"runner_{self.name}_to", "")

    @property
    def max_cards(self) -> int:
        return getattr(self.config, f"max_cards_{self.name}", 5)

    @property
    def agent(self) -> str:
        return getattr(self.config, f"runner_{self.name}_agent", "") or self.config.claude_agent

    # -- Main loop --

    def run(self) -> int:
        """Execute the runner loop. Returns total cards processed."""
        log_info(f"{self.name.capitalize()}: checking {self.from_status} lane...")
        log_event("runner_started", self.config, runner_name=self.name)

        cards_processed = 0
        start_at = 0
        skip_retries = 0

        while True:
            issue_ids = self.adapter.get_cards_in_status(
                self.from_status, self.max_cards, start_at
            )

            if not issue_ids:
                if start_at == 0:
                    log_info(f"No cards in {self.from_status}. Nothing to {self.name}.")
                break

            batch_processed = 0

            for issue_id in issue_ids:
                try:
                    issue_key = self.adapter.get_card_key(issue_id)
                except Exception:
                    log_warn(f"Failed to fetch key for issue {issue_id}. Skipping.")
                    continue

                try:
                    outcome = self.process_card(issue_key)
                except ClaudeRateLimited:
                    raise  # propagate to loop — stops all runners
                except Exception as exc:
                    log_error(f"Unexpected error processing {issue_key}: {exc}")
                    log_event(
                        "card_processed", self.config,
                        runner_name=self.name,
                        card_key=issue_key, outcome="failed",
                    )
                    continue

                if outcome == "skipped":
                    log_event(
                        "card_processed", self.config,
                        runner_name=self.name,
                        card_key=issue_key, outcome="skipped",
                    )
                    continue

                if outcome == "failed":
                    log_event(
                        "card_processed", self.config,
                        runner_name=self.name,
                        card_key=issue_key, outcome="failed",
                    )
                    continue

                # success
                log_event(
                    "card_processed", self.config,
                    runner_name=self.name,
                    card_key=issue_key, outcome="success",
                )
                batch_processed += 1
                cards_processed += 1

            if batch_processed > 0:
                break

            skip_retries += 1
            if skip_retries >= self.config.max_skip_retries:
                log_info(
                    f"Reached max skip retries ({self.config.max_skip_retries}). Moving on."
                )
                break

            start_at += self.max_cards
            log_info(
                f"All cards skipped in batch. Fetching next batch "
                f"(retry {skip_retries}/{self.config.max_skip_retries})..."
            )

        log_event(
            "runner_completed", self.config,
            runner_name=self.name,
            cards_processed=str(cards_processed),
        )
        return cards_processed

    # -- Abstract method --

    @abstractmethod
    def process_card(self, issue_key: str) -> str:
        """Process a single card.

        Returns:
            "success" -- card was processed and should be counted
            "skipped" -- card was intentionally skipped (type filter, already processed, etc.)
            "failed"  -- card processing failed

        Raises:
            ClaudeRateLimited -- when Claude returns rate limit (breaks the batch loop)
        """

    # -- Helpers --

    def _render_and_run_claude(
        self,
        template_name: str,
        extra_vars: dict[str, str],
        work_dir: str = "",
    ) -> tuple[int, str]:
        """Render a prompt template and run Claude.

        Args:
            template_name: Name of template file in prompts/ (e.g., "refine.md")
            extra_vars: Template variables to substitute (e.g., CARD_KEY, CARD_TITLE)
            work_dir: Optional working directory for Claude

        Returns:
            (return_code, result_text) -- rc is 0=success, 1=failure, 2=rate_limit
        """
        template_path = Path(self.config.sorta_root) / "prompts" / template_name
        prompt = render_template(template_path, **extra_vars)

        prompt_file = Path(tempfile.mktemp(suffix=".prompt.md"))
        result_file = Path(tempfile.mktemp(suffix=".result.md"))

        try:
            prompt_file.write_text(prompt, encoding="utf-8")

            log_event("claude_started", self.config, runner_name=self.name)

            rc = run_claude(prompt_file, result_file, work_dir, self.agent)

            log_event(
                "claude_completed", self.config,
                runner_name=self.name,
                exit_code=str(rc),
            )

            if rc == 2:
                # Rate limited -- write the rate file so the loop can sleep
                reset_epoch = get_rate_limit_reset()
                set_rate_limited(self.config.sorta_root, reset_epoch)
                prompt_file.unlink(missing_ok=True)
                result_file.unlink(missing_ok=True)
                return rc, ""

            if rc != 0:
                prompt_file.unlink(missing_ok=True)
                result_file.unlink(missing_ok=True)
                return rc, ""

            result_text = result_file.read_text(encoding="utf-8") if result_file.exists() else ""
            return 0, result_text
        finally:
            prompt_file.unlink(missing_ok=True)
            result_file.unlink(missing_ok=True)

    def _transition(self, issue_key: str, verb: str) -> None:
        """Transition a card to the runner's target status."""
        from sortafit.runner_lib import runner_transition
        runner_transition(issue_key, self.to_status, verb, self.config, self.adapter)

    def _timestamp(self) -> str:
        """Return current timestamp matching bash date '+%Y-%m-%d %H:%M'."""
        return datetime.now().strftime("%Y-%m-%d %H:%M")
