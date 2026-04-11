"""Sorta.Fit code runner -- implements cards in isolated git worktrees.

Port of runners/code.sh. The most complex runner: fetch origin -> for each card:
create branch slug -> setup_worktree -> render code.md -> run Claude in worktree ->
check for commits -> push branch -> check for existing PR (rework) or create new PR ->
transition -> cleanup worktree.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from sortafit.events import log_event
from sortafit.runners.base import BaseRunner, ClaudeRateLimited
from sortafit.runner_lib import runner_transition, setup_worktree
from sortafit.utils import (
    extract_pr_url,
    find_gh,
    log_error,
    log_info,
    log_step,
    log_warn,
    slugify,
)


class CodeRunner(BaseRunner):
    name = "code"

    def __init__(self, config, adapter) -> None:
        super().__init__(config, adapter)
        self._gh = find_gh()
        self._repo_root = config.target_repo
        self._worktree_dir = str(Path(config.sorta_root) / ".worktrees")

    def run(self) -> int:
        """Override to add fetch origin before the main loop."""
        log_info(f"Fetching latest {self.config.git_base_branch}...")
        result = subprocess.run(
            ["git", "-C", self._repo_root, "fetch", "origin", self.config.git_base_branch],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode != 0:
            log_error(f"Could not fetch origin/{self.config.git_base_branch}")
            return 0

        cards = super().run()

        # Clean up worktree dir if empty
        try:
            worktree_path = Path(self._worktree_dir)
            if worktree_path.is_dir() and not any(worktree_path.iterdir()):
                worktree_path.rmdir()
        except Exception:
            pass

        return cards

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

        log_step(f"Implementing: {issue_key} -- {title}")

        branch_slug = slugify(title)
        branch_name = f"claude/{issue_key}-{branch_slug}"

        # Setup worktree
        try:
            card_worktree = setup_worktree(
                issue_key, branch_name, self._repo_root,
                self._worktree_dir, self.config,
            )
        except Exception:
            card_worktree = None

        if not card_worktree:
            log_error(f"Worktree creation failed for {issue_key}")
            self.adapter.add_comment(
                issue_key,
                f"Sorta.Fit: worktree creation failed on {self._timestamp()}.",
            )
            log_event("card_processed", self.config, runner_name=self.name,
                      card_key=issue_key, outcome="failed")
            return "failed"

        # Run Claude in worktree
        rc, implementation_result = self._render_and_run_claude("code.md", {
            "CARD_KEY": issue_key,
            "CARD_TITLE": title,
            "CARD_DESCRIPTION": description,
            "CARD_COMMENTS": comments,
            "BRANCH_NAME": branch_name,
            "BASE_BRANCH": self.config.git_base_branch,
        }, work_dir=card_worktree)

        if rc == 2:
            self._remove_worktree(card_worktree)
            raise ClaudeRateLimited()

        if rc != 0:
            log_error(f"Claude failed for {issue_key}")
            self.adapter.add_comment(
                issue_key,
                f"Sorta.Fit: implementation failed on {self._timestamp()}. "
                f"Manual intervention needed.",
            )
            self._remove_worktree(card_worktree)
            return "failed"

        # Check for commits
        try:
            result = subprocess.run(
                ["git", "-C", self._repo_root, "log",
                 f"origin/{self.config.git_base_branch}..{branch_name}", "--oneline"],
                capture_output=True, text=True, encoding="utf-8",
            )
            commit_count = len([l for l in result.stdout.strip().splitlines() if l.strip()])
        except Exception:
            commit_count = 0

        if commit_count == 0:
            log_warn(f"No commits on branch for {issue_key}.")
            self.adapter.add_comment(
                issue_key,
                f"Sorta.Fit: no commits produced on {self._timestamp()}. Review needed.",
            )
            self._remove_worktree(card_worktree)
            return "failed"

        log_info(f"{commit_count} commit(s) on branch.")

        # Push branch to remote
        push_result = subprocess.run(
            ["git", "-C", card_worktree, "push", "-u", "origin", branch_name],
            capture_output=True, text=True, encoding="utf-8",
        )
        if push_result.returncode != 0:
            log_error(f"Failed to push branch {branch_name} for {issue_key}")
            self.adapter.add_comment(
                issue_key,
                f"Sorta.Fit: push failed on {self._timestamp()}. Branch: {branch_name}",
            )
            self._remove_worktree(card_worktree)
            return "failed"

        # Prepare PR body
        pr_body = (
            f"## {issue_key}: {title}\n\n"
            f"### Implementation Notes\n"
            f"{implementation_result}\n\n"
            f"### Test Plan\n"
            f"- [ ] All tests pass\n"
            f"- [ ] Build succeeds\n"
            f"- [ ] Acceptance criteria met\n"
            f"- [ ] Manual QA\n\n"
            f"---\n"
            f"Automated by Sorta.Fit"
        )

        pr_body_file = Path(tempfile.mktemp(suffix=".pr-body.md"))
        try:
            pr_body_file.write_text(pr_body, encoding="utf-8")

            # Check for existing open PR on this branch
            pr_url = self._handle_pr(issue_key, title, branch_name, pr_body_file)
        finally:
            pr_body_file.unlink(missing_ok=True)

        self._transition(issue_key, "implemented")
        self._remove_worktree(card_worktree)
        return "success"

    def _handle_pr(
        self, issue_key: str, title: str, branch_name: str, pr_body_file: Path,
        pr_base: str = "",
    ) -> str:
        """Create or update a PR. Returns the PR URL."""
        if not pr_base:
            pr_base = self.config.git_base_branch

        # Check for existing open PR on this branch
        existing_pr_url = ""
        try:
            result = subprocess.run(
                [self._gh, "pr", "list", "--head", branch_name,
                 "--state", "open", "--json", "url", "--jq", ".[0].url"],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            existing_pr_url = result.stdout.strip()
            if existing_pr_url == "null":
                existing_pr_url = ""
        except Exception:
            pass

        if existing_pr_url:
            return self._update_existing_pr(issue_key, existing_pr_url, pr_body_file)
        else:
            return self._create_new_pr(issue_key, title, branch_name, pr_body_file, pr_base=pr_base)

    def _update_existing_pr(
        self, issue_key: str, pr_url: str, pr_body_file: Path,
    ) -> str:
        """Rework case -- update existing PR."""
        pr_edit_ok = False
        try:
            result = subprocess.run(
                [self._gh, "pr", "edit", pr_url, "--body-file", str(pr_body_file)],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            pr_edit_ok = result.returncode == 0
        except Exception:
            log_warn(f"Failed to update PR body for {pr_url}")

        # Post rework comment
        try:
            subprocess.run(
                [self._gh, "pr", "comment", pr_url,
                 "--body", "Rework pushed by Sorta.Fit \u2014 ready for re-review"],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
        except Exception:
            log_warn(f"Failed to post rework comment on {pr_url}")

        if pr_edit_ok:
            log_info(f"PR updated: {pr_url}")
            self.adapter.add_comment(
                issue_key,
                f"PR updated: {pr_url} \u2014 Rework pushed by Sorta.Fit {self._timestamp()}",
            )
            log_event(
                "pr_updated", self.config,
                runner_name=self.name,
                card_key=issue_key, pr_url=pr_url,
            )
        else:
            log_warn("PR body update failed, but rework commits pushed to branch")
            self.adapter.add_comment(
                issue_key,
                f"Rework pushed to branch (PR body update failed): {pr_url} "
                f"\u2014 Sorta.Fit {self._timestamp()}",
            )
            log_event(
                "pr_updated", self.config,
                runner_name=self.name,
                card_key=issue_key, pr_url=pr_url,
            )

        return pr_url

    def _create_new_pr(
        self, issue_key: str, title: str, branch_name: str, pr_body_file: Path,
        pr_base: str,
    ) -> str:
        """Create a new PR with retry (GitHub may not have indexed the pushed ref yet)."""
        pr_url = ""
        pr_created = False

        for attempt in range(1, 4):
            try:
                result = subprocess.run(
                    [self._gh, "pr", "create",
                     "--title", f"{issue_key}: {title}",
                     "--body-file", str(pr_body_file),
                     "--base", pr_base,
                     "--head", branch_name],
                    capture_output=True, text=True, encoding="utf-8", timeout=60,
                )
                if result.returncode == 0:
                    pr_url = result.stdout.strip()
                    pr_created = True
                    break
                else:
                    pr_url = result.stdout + result.stderr
            except Exception as exc:
                pr_url = str(exc)

            if attempt < 3:
                log_warn(f"PR creation attempt {attempt} failed for {issue_key}, retrying in 5s...")
                time.sleep(5)

        if not pr_created:
            log_error(f"PR creation failed for {issue_key} after 3 attempts: {pr_url}")
            self.adapter.add_comment(
                issue_key,
                f"Sorta.Fit: branch pushed but PR creation failed on {self._timestamp()}. "
                f"Branch: {branch_name}",
            )
            return ""

        log_info(f"PR created: {pr_url}")
        self.adapter.add_comment(
            issue_key,
            f"PR opened: {pr_url} \u2014 Sorta.Fit {self._timestamp()}",
        )
        log_event(
            "pr_opened", self.config,
            runner_name=self.name,
            card_key=issue_key, pr_url=pr_url,
        )
        return pr_url

    def _remove_worktree(self, worktree_path: str) -> None:
        """Force-remove a git worktree."""
        try:
            subprocess.run(
                ["git", "-C", self._repo_root, "worktree", "remove", worktree_path, "--force"],
                capture_output=True, text=True, encoding="utf-8",
            )
        except Exception:
            pass
