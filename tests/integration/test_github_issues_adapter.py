"""Integration tests for GitHub Issues adapter -- port of github-issues-adapter-validation.bats"""
import json
from unittest.mock import patch

import pytest
import responses

from sortafit.adapters.github_issues import GitHubIssuesAdapter
from sortafit.config import Config


@pytest.fixture
def gh_config(tmp_path):
    return Config(
        board_adapter="github-issues",
        board_domain="github.com",
        board_project_key="owner/repo",
        board_api_token="test-token",
        target_repo=str(tmp_path),
        sorta_root=str(tmp_path),
    )


@pytest.fixture
def gh_adapter(gh_config):
    # Force non-CLI mode for testing
    with patch("sortafit.adapters.github_issues.find_gh", return_value="gh"):
        adapter = GitHubIssuesAdapter(gh_config)
    adapter.use_cli = False
    return adapter


class TestGitHubIssuesErrorHandling:
    @responses.activate
    def test_200_success(self, gh_adapter):
        responses.add(responses.GET, "https://api.github.com/repos/owner/repo/issues/1",
            json={"number": 1, "title": "Test"}, status=200)
        assert gh_adapter.get_card_title("GH-1") == "Test"

    @responses.activate
    def test_401_unauthorized(self, gh_adapter):
        responses.add(responses.GET, "https://api.github.com/repos/owner/repo/issues/1",
            json={"message": "Unauthorized"}, status=401)
        with pytest.raises(Exception):
            gh_adapter.get_card_title("GH-1")

    @responses.activate
    def test_404_not_found(self, gh_adapter):
        responses.add(responses.GET, "https://api.github.com/repos/owner/repo/issues/1",
            json={"message": "Not Found"}, status=404)
        with pytest.raises(Exception):
            gh_adapter.get_card_title("GH-1")

    @responses.activate
    def test_500_server_error(self, gh_adapter):
        responses.add(responses.GET, "https://api.github.com/repos/owner/repo/issues/1",
            json={"message": "Server Error"}, status=500)
        with pytest.raises(Exception):
            gh_adapter.get_card_title("GH-1")

    @responses.activate
    def test_html_response(self, gh_adapter):
        responses.add(responses.GET, "https://api.github.com/repos/owner/repo/issues/1",
            body="<html>Login</html>", status=200, content_type="text/html")
        with pytest.raises(Exception):
            gh_adapter.get_card_title("GH-1")

    @responses.activate
    def test_network_error(self, gh_adapter):
        responses.add(responses.GET, "https://api.github.com/repos/owner/repo/issues/1",
            body=ConnectionError("Network error"))
        with pytest.raises(Exception):
            gh_adapter.get_card_title("GH-1")

    def test_empty_token_no_auth_header(self, tmp_path):
        config = Config(
            board_adapter="github-issues", board_domain="github.com",
            board_project_key="owner/repo", board_api_token="",
            target_repo=str(tmp_path), sorta_root=str(tmp_path),
        )
        with patch("sortafit.adapters.github_issues.find_gh", return_value="gh"):
            adapter = GitHubIssuesAdapter(config)
        adapter.use_cli = False
        assert "Authorization" not in adapter.session.headers

    def test_ghe_domain_api_base(self, tmp_path):
        config = Config(
            board_adapter="github-issues", board_domain="github.mycompany.com",
            board_project_key="owner/repo", board_api_token="test-token",
            target_repo=str(tmp_path), sorta_root=str(tmp_path),
        )
        with patch("sortafit.adapters.github_issues.find_gh", return_value="gh"):
            adapter = GitHubIssuesAdapter(config)
        assert adapter.api_base == "https://github.mycompany.com/api/v3"
