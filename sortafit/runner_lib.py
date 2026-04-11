"""Sorta.Fit shared runner library — port of core/runner-lib.sh"""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from sortafit.claude import run_claude
from sortafit.config import Config
from sortafit.events import log_event
from sortafit.utils import find_gh, log_error, log_info, log_warn


def runner_transition(
    issue_key: str,
    target_status: str,
    verb: str,
    config: Config,
    adapter,
) -> None:
    """Transition a card to a target status. Port of runner_transition()."""
    if not target_status:
        log_info(f"Done: {issue_key} {verb} (no transition configured)")
        log_event("card_transitioned", config, card_key=issue_key, target_status="", transition_configured="false")
        return

    safe_status = re.sub(r"[^a-zA-Z0-9_]", "_", target_status)
    transition_var = f"TRANSITION_TO_{safe_status}"
    transition_id = config.adapter_transitions.get(transition_var, "")

    if transition_id:
        adapter.transition(issue_key, transition_id)
        log_info(f"Done: {issue_key} {verb} and moved to {target_status}")
        log_event("card_transitioned", config, card_key=issue_key, target_status=target_status, transition_configured="true")
    else:
        log_warn(f"No transition mapping found for status {target_status} — card {verb} but not moved. Add {transition_var} to your adapter config.")
        log_event("card_transitioned", config, card_key=issue_key, target_status=target_status, transition_configured="false")


def setup_worktree(
    issue_key: str,
    branch_name: str,
    repo_root: str,
    worktree_dir: str,
    config: Config,
) -> str | None:
    """Set up a git worktree for a card. Port of setup_worktree().

    Returns worktree path on success, None on failure.
    """
    protected = ["main", "master", "dev", "develop"]
    if branch_name in protected:
        log_error("Branch name matches protected branch. Skipping.")
        return None

    card_worktree = os.path.join(worktree_dir, issue_key)

    # Clean up leftover worktree
    if os.path.isdir(card_worktree):
        log_warn("Cleaning up leftover worktree...")
        result = subprocess.run(
            ["git", "-C", repo_root, "worktree", "remove", card_worktree, "--force"],
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            try:
                shutil.rmtree(card_worktree)
            except Exception:
                log_warn(f"Locked worktree for {issue_key}. Using alternate directory.")
                card_worktree = f"{card_worktree}-{int(time.time())}"

    # Create or reuse branch
    result = subprocess.run(
        ["git", "-C", repo_root, "rev-parse", "--verify", branch_name],
        capture_output=True, text=True, encoding="utf-8"
    )
    effective_base = f"origin/{config.git_base_branch}"

    branch_existed = result.returncode == 0
    if branch_existed:
        log_info(f"Branch {branch_name} already exists (retry/rework case).")
    else:
        log_info(f"Creating branch: {branch_name} from {effective_base}")
        result = subprocess.run(
            ["git", "-C", repo_root, "branch", branch_name, effective_base],
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            log_error(f"Could not create branch: {result.stderr}")
            return None

    # Create worktree
    os.makedirs(worktree_dir, exist_ok=True)
    subprocess.run(["git", "-C", repo_root, "worktree", "prune"], capture_output=True)
    result = subprocess.run(
        ["git", "-C", repo_root, "worktree", "add", card_worktree, branch_name],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        log_error(f"Could not create worktree for {issue_key}")
        return None

    # Merge base branch into existing branches to pick up upstream changes
    if branch_existed:
        log_info(f"Merging {effective_base} into {branch_name}...")
        fetch_result = subprocess.run(
            ["git", "-C", card_worktree, "fetch", "origin"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if fetch_result.returncode != 0:
            log_warn(f"Fetch failed: {fetch_result.stderr}")
        else:
            merge_result = subprocess.run(
                ["git", "-C", card_worktree, "merge", effective_base,
                 "--no-edit", "-m", f"Merge {effective_base} into {branch_name}"],
                capture_output=True, text=True, encoding="utf-8",
            )
            if merge_result.returncode != 0:
                log_warn(f"Merge of {effective_base} had conflicts — aborting merge.")
                subprocess.run(
                    ["git", "-C", card_worktree, "merge", "--abort"],
                    capture_output=True, text=True, encoding="utf-8",
                )
            elif "Already up to date" in merge_result.stdout:
                log_info(f"Branch already up to date with {effective_base}.")
            else:
                log_info(f"Merged {effective_base} into {branch_name}.")

    # Copy Claude permissions
    settings_src = os.path.join(repo_root, ".claude", "settings.local.json")
    if os.path.isfile(settings_src):
        settings_dst_dir = os.path.join(card_worktree, ".claude")
        os.makedirs(settings_dst_dir, exist_ok=True)
        shutil.copy2(settings_src, os.path.join(settings_dst_dir, "settings.local.json"))
    else:
        log_warn("Missing .claude/settings.local.json — Claude Code won't have permissions.")

    # Install dependencies (non-fatal — worktree is already created)
    # shell=True needed on Windows where npm is npm.cmd
    log_info("Installing dependencies...")
    try:
        result = subprocess.run(
            "npm ci --silent", cwd=card_worktree, shell=True,
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode != 0:
            log_info("npm ci failed, trying npm install...")
            subprocess.run(
                "npm install --silent", cwd=card_worktree, shell=True,
                capture_output=True, text=True, encoding="utf-8"
            )
    except Exception as e:
        log_warn(f"Dependency install failed: {e}")

    return card_worktree


def run_claude_safe(
    prompt_file: Path,
    result_file: Path,
    work_dir: str = "",
    agent: str = "",
    config: Config | None = None,
    runner_name: str = "",
) -> int:
    """Run Claude with cleanup on failure. Port of run_claude_safe().

    Returns 0=success, 1=error, 2=rate-limited.
    """
    start_time = int(time.time())
    if config:
        log_event("claude_started", config, runner_name=runner_name)

    rc = run_claude(prompt_file, result_file, work_dir, agent)

    if config:
        duration = int(time.time()) - start_time
        log_event("claude_completed", config, runner_name=runner_name,
                  duration_s=str(duration), exit_code=str(rc))

    if rc != 0:
        prompt_file.unlink(missing_ok=True)
        result_file.unlink(missing_ok=True)

    return rc


def check_pr_review_state(pr_url: str, expected: str) -> bool:
    """Check if a PR has a specific review state. Port of check_pr_review_state()."""
    gh_cmd = find_gh()
    result = subprocess.run(
        [gh_cmd, "pr", "view", pr_url, "--json", "reviewDecision", "--jq", ".reviewDecision"],
        capture_output=True, text=True, encoding="utf-8"
    )
    state = result.stdout.strip()
    if state == expected:
        return True

    # Fallback: check reviews directly
    if not state or state == "null":
        result = subprocess.run(
            [gh_cmd, "pr", "view", pr_url, "--json", "reviews", "--jq", ".reviews[-1].state"],
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.stdout.strip() == expected:
            return True

    return False
