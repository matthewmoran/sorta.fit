"""Unit tests for sortafit.runner_lib — port of tests/unit/runner-lib.bats"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sortafit.config import Config
from sortafit.events import log_event
from sortafit.runner_lib import runner_transition, setup_worktree
from sortafit.utils import extract_pr_url


class TestRunnerTransition:
    def _make_config(self, tmp_path, transitions=None):
        config = Config(
            board_adapter="jira",
            board_domain="test.atlassian.net",
            board_project_key="TEST",
            board_api_token="test-token",
            target_repo=str(tmp_path),
            event_logging="on",
            adapter_transitions=transitions or {},
            sorta_root=str(tmp_path),
        )
        (tmp_path / ".sorta").mkdir(exist_ok=True)
        return config

    def test_empty_target_status(self, tmp_path):
        config = self._make_config(tmp_path)
        adapter = MagicMock()
        runner_transition("TEST-1", "", "refined", config, adapter)
        adapter.transition.assert_not_called()

    def test_valid_target_with_mapping(self, tmp_path):
        config = self._make_config(tmp_path, {"TRANSITION_TO_10070": "5"})
        adapter = MagicMock()
        runner_transition("TEST-1", "10070", "refined", config, adapter)
        adapter.transition.assert_called_once_with("TEST-1", "5")

    def test_target_without_mapping_warns(self, tmp_path):
        config = self._make_config(tmp_path)
        adapter = MagicMock()
        runner_transition("TEST-1", "99999", "refined", config, adapter)
        adapter.transition.assert_not_called()

    def test_status_with_colons_sanitized(self, tmp_path):
        config = self._make_config(tmp_path, {"TRANSITION_TO_status_todo": "status:todo"})
        adapter = MagicMock()
        runner_transition("GH-1", "status:todo", "refined", config, adapter)
        adapter.transition.assert_called_once_with("GH-1", "status:todo")

    def test_status_with_hyphens_sanitized(self, tmp_path):
        config = self._make_config(tmp_path, {"TRANSITION_TO_f2b1c3d4_5678_9abc": "f2b1c3d4-5678-9abc"})
        adapter = MagicMock()
        runner_transition("ENG-1", "f2b1c3d4-5678-9abc", "refined", config, adapter)
        adapter.transition.assert_called_once_with("ENG-1", "f2b1c3d4-5678-9abc")

    def test_emits_event_with_mapping(self, tmp_path):
        config = self._make_config(tmp_path, {"TRANSITION_TO_10070": "5"})
        adapter = MagicMock()
        runner_transition("TEST-1", "10070", "refined", config, adapter)
        events_file = tmp_path / ".sorta" / "events.jsonl"
        assert events_file.exists()
        lines = events_file.read_text().strip().split("\n")
        found = any(
            json.loads(l)["event"] == "card_transitioned"
            and json.loads(l)["data"]["card_key"] == "TEST-1"
            and json.loads(l)["data"]["transition_configured"] == "true"
            for l in lines
        )
        assert found

    def test_emits_event_empty_target(self, tmp_path):
        config = self._make_config(tmp_path)
        adapter = MagicMock()
        runner_transition("TEST-2", "", "refined", config, adapter)
        events_file = tmp_path / ".sorta" / "events.jsonl"
        lines = events_file.read_text().strip().split("\n")
        found = any(
            json.loads(l)["event"] == "card_transitioned"
            and json.loads(l)["data"]["transition_configured"] == "false"
            for l in lines
        )
        assert found


class TestExtractPrUrlRunnerLib:
    """Test the first-match mode used by runner-lib (vs last-match in utils)."""

    def test_single_url(self):
        assert extract_pr_url("PR: https://github.com/owner/repo/pull/42", last=False) == "https://github.com/owner/repo/pull/42"

    def test_multiple_returns_first(self):
        text = "First: https://github.com/owner/repo/pull/1\nSecond: https://github.com/owner/repo/pull/2"
        assert extract_pr_url(text, last=False) == "https://github.com/owner/repo/pull/1"

    def test_no_url(self):
        assert extract_pr_url("no links here", last=False) == ""


class TestSetupWorktreeSafety:
    def test_rejects_protected_branches(self, tmp_path):
        from sortafit.runner_lib import setup_worktree
        config = Config(
            board_adapter="jira", board_domain="test.atlassian.net",
            board_project_key="TEST", target_repo=str(tmp_path),
            sorta_root=str(tmp_path),
        )
        for branch in ["main", "master", "dev", "develop"]:
            result = setup_worktree("TEST-1", branch, str(tmp_path), str(tmp_path / "worktrees"), config)
            assert result is None


