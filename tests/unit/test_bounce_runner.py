"""Tests for the bounce runner's rework-after-review detection."""
import json
from unittest.mock import MagicMock, patch

import pytest

from sortafit.config import Config
from sortafit.runners.bounce import BounceRunner


def _make_config(**overrides):
    defaults = dict(
        board_adapter="jira",
        board_domain="test.atlassian.net",
        board_api_token="test-token-do-not-use",
        board_project_key="TEST",
        target_repo="/tmp/repo",
        sorta_root="/tmp/sorta",
        runner_bounce_from="10109",
        runner_bounce_to="10110",
        max_bounces=3,
        runner_bounce_escalate="",
        max_cards_bounce=10,
        event_logging="off",
    )
    defaults.update(overrides)
    return Config(**defaults)


@pytest.fixture
def mock_adapter():
    adapter = MagicMock()
    adapter.get_cards_in_status.return_value = []
    return adapter


@pytest.fixture
def bounce_runner(mock_adapter):
    config = _make_config()
    with patch("sortafit.runners.bounce.find_gh", return_value="gh"):
        runner = BounceRunner(config, mock_adapter)
    return runner


class TestHasCommitsAfterLastReview:
    """Tests for BounceRunner._has_commits_after_last_review."""

    def test_new_commits_after_review(self, bounce_runner):
        """Should return True when PR HEAD differs from last reviewed commit."""
        gh_output = json.dumps({
            "reviews": [
                {"state": "CHANGES_REQUESTED", "commit": {"oid": "abc123"}},
            ],
            "commits": [
                {"oid": "abc123"},
                {"oid": "def456"},
            ],
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=gh_output)
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is True

    def test_no_commits_after_review(self, bounce_runner):
        """Should return False when PR HEAD matches the reviewed commit."""
        gh_output = json.dumps({
            "reviews": [
                {"state": "CHANGES_REQUESTED", "commit": {"oid": "abc123"}},
            ],
            "commits": [
                {"oid": "abc123"},
            ],
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=gh_output)
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is False

    def test_multiple_reviews_uses_last(self, bounce_runner):
        """Should compare against the last CHANGES_REQUESTED review, not the first."""
        gh_output = json.dumps({
            "reviews": [
                {"state": "CHANGES_REQUESTED", "commit": {"oid": "aaa111"}},
                {"state": "CHANGES_REQUESTED", "commit": {"oid": "bbb222"}},
            ],
            "commits": [
                {"oid": "aaa111"},
                {"oid": "bbb222"},
                {"oid": "ccc333"},
            ],
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=gh_output)
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is True

    def test_multiple_reviews_head_matches_last(self, bounce_runner):
        """Should return False when HEAD matches the last review even if earlier reviews differ."""
        gh_output = json.dumps({
            "reviews": [
                {"state": "CHANGES_REQUESTED", "commit": {"oid": "aaa111"}},
                {"state": "CHANGES_REQUESTED", "commit": {"oid": "bbb222"}},
            ],
            "commits": [
                {"oid": "aaa111"},
                {"oid": "bbb222"},
            ],
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=gh_output)
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is False

    def test_no_changes_requested_reviews(self, bounce_runner):
        """Should return False when there are no CHANGES_REQUESTED reviews."""
        gh_output = json.dumps({
            "reviews": [
                {"state": "APPROVED", "commit": {"oid": "abc123"}},
            ],
            "commits": [
                {"oid": "def456"},
            ],
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=gh_output)
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is False

    def test_no_reviews(self, bounce_runner):
        """Should return False when there are no reviews at all."""
        gh_output = json.dumps({"reviews": [], "commits": [{"oid": "abc123"}]})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=gh_output)
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is False

    def test_no_commits(self, bounce_runner):
        """Should return False when there are no commits."""
        gh_output = json.dumps({
            "reviews": [{"state": "CHANGES_REQUESTED", "commit": {"oid": "abc123"}}],
            "commits": [],
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=gh_output)
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is False

    def test_gh_failure(self, bounce_runner):
        """Should return False when gh command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is False

    def test_gh_exception(self, bounce_runner):
        """Should return False when gh command raises an exception."""
        with patch("subprocess.run", side_effect=Exception("timeout")):
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is False

    def test_missing_commit_field_in_review(self, bounce_runner):
        """Should return False when review has no commit field."""
        gh_output = json.dumps({
            "reviews": [{"state": "CHANGES_REQUESTED"}],
            "commits": [{"oid": "abc123"}],
        })
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=gh_output)
            assert bounce_runner._has_commits_after_last_review("https://github.com/o/r/pull/1") is False
