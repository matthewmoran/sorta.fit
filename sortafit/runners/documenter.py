"""Sorta.Fit documenter runner -- generates and maintains project docs from card specs.

Port of runners/documenter.sh. Like the code runner but for docs: skip if already
documented -> setup worktree -> render documenter.md -> run Claude -> check commits ->
push + create PR -> transition.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from sortafit.events import log_event
from sortafit.runners.base import BaseRunner, ClaudeRateLimited
from sortafit.runner_lib import setup_worktree
from sortafit.utils import (
    find_gh,
    log_error,
    log_info,
    log_step,
    log_warn,
    slugify,
)


class DocumenterRunner(BaseRunner):
    name = "documenter"

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

        # Skip if already documented
        if "Docs PR opened" in comments:
            log_info(f"{issue_key} already documented. Skipping.")
            return "skipped"
        if "no documentation changes needed" in comments:
            log_info(f"{issue_key} already checked -- no docs needed. Skipping.")
            return "skipped"

        log_step(f"Documenting: {issue_key} -- {title}")

        branch_slug = slugify(title)
        branch_name = f"claude/{issue_key}-docs-{branch_slug}"

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
        rc, documentation_result = self._render_and_run_claude("documenter.md", {
            "CARD_KEY": issue_key,
            "CARD_TITLE": title,
            "CARD_DESCRIPTION": description,
            "CARD_COMMENTS": comments,
            "BRANCH_NAME": branch_name,
            "BASE_BRANCH": self.config.git_base_branch,
            "DOCS_DIR": self.config.docs_dir,
            "DOCS_ORGANIZE_BY": self.config.docs_organize_by,
        }, work_dir=card_worktree)

        if rc == 2:
            self._remove_worktree(card_worktree)
            raise ClaudeRateLimited()

        if rc != 0:
            log_error(f"Claude failed for {issue_key}")
            self.adapter.add_comment(
                issue_key,
                f"Sorta.Fit: documentation generation failed on {self._timestamp()}. "
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
            log_warn(f"No commits on branch for {issue_key} -- no documentation changes needed.")
            self.adapter.add_comment(
                issue_key,
                f"Sorta.Fit: no documentation changes needed on {self._timestamp()}.",
            )
            self._transition(issue_key, "documented")
            self._remove_worktree(card_worktree)
            return "success"

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

        # Create PR
        pr_body = (
            f"## {issue_key}: {title} -- Documentation\n\n"
            f"### Documentation Changes\n"
            f"{documentation_result}\n\n"
            f"### Review Checklist\n"
            f"- [ ] Documentation is accurate and matches the feature spec\n"
            f"- [ ] Existing docs updated where appropriate (not duplicated)\n"
            f"- [ ] File placement follows `{self.config.docs_dir}` convention\n\n"
            f"---\n"
            f"Automated by Sorta.Fit"
        )

        pr_body_file = Path(tempfile.mktemp(suffix=".pr-body.md"))
        try:
            pr_body_file.write_text(pr_body, encoding="utf-8")

            result = subprocess.run(
                [self._gh, "pr", "create",
                 "--title", f"{issue_key}: docs -- {title}",
                 "--body-file", str(pr_body_file),
                 "--base", self.config.git_base_branch,
                 "--head", branch_name],
                capture_output=True, text=True, encoding="utf-8", timeout=60,
            )
        finally:
            pr_body_file.unlink(missing_ok=True)

        if result.returncode != 0:
            pr_output = result.stdout + result.stderr
            log_error(f"PR creation failed for {issue_key}: {pr_output}")
            self.adapter.add_comment(
                issue_key,
                f"Sorta.Fit: branch pushed but PR creation failed on {self._timestamp()}. "
                f"Branch: {branch_name}",
            )
            self._transition(issue_key, "documented")
            self._remove_worktree(card_worktree)
            return "failed"

        pr_url = result.stdout.strip()
        log_info(f"PR created: {pr_url}")
        log_event(
            "pr_opened", self.config,
            runner_name=self.name,
            card_key=issue_key, pr_url=pr_url,
        )

        self.adapter.add_comment(
            issue_key,
            f"Docs PR opened: {pr_url} -- Sorta.Fit {self._timestamp()}",
        )

        self._transition(issue_key, "documented")
        self._remove_worktree(card_worktree)
        return "success"

    def _remove_worktree(self, worktree_path: str) -> None:
        """Force-remove a git worktree."""
        try:
            subprocess.run(
                ["git", "-C", self._repo_root, "worktree", "remove", worktree_path, "--force"],
                capture_output=True, text=True, encoding="utf-8",
            )
        except Exception:
            pass
