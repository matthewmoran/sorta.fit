"""Integration tests for Jira adapter error handling -- port of adapter-validation.bats"""
import pytest
import responses

from sortafit.adapters.jira import JiraAdapter
from sortafit.config import Config


@pytest.fixture
def jira_config(tmp_path):
    return Config(
        board_adapter="jira",
        board_domain="test.atlassian.net",
        board_project_key="TEST",
        board_api_token="test-token",
        board_email="test@example.com",
        target_repo=str(tmp_path),
        sorta_root=str(tmp_path),
    )


@pytest.fixture
def jira(jira_config):
    return JiraAdapter(jira_config)


class TestJiraErrorHandling:
    @responses.activate
    def test_200_success(self, jira):
        responses.add(responses.GET, "https://test.atlassian.net/rest/api/3/issue/TEST-1",
            json={"key": "TEST-1", "fields": {"summary": "Test issue"}}, status=200)
        assert jira.get_card_title("TEST-1") == "Test issue"

    @responses.activate
    def test_401_unauthorized(self, jira):
        responses.add(responses.GET, "https://test.atlassian.net/rest/api/3/issue/TEST-1",
            json={"errorMessages": ["Unauthorized"]}, status=401)
        with pytest.raises(Exception):
            jira.get_card_title("TEST-1")

    @responses.activate
    def test_404_not_found(self, jira):
        responses.add(responses.GET, "https://test.atlassian.net/rest/api/3/issue/TEST-1",
            json={"errorMessages": ["Not found"]}, status=404)
        with pytest.raises(Exception):
            jira.get_card_title("TEST-1")

    @responses.activate
    def test_500_server_error(self, jira):
        responses.add(responses.GET, "https://test.atlassian.net/rest/api/3/issue/TEST-1",
            json={"errorMessages": ["Server error"]}, status=500)
        with pytest.raises(Exception):
            jira.get_card_title("TEST-1")

    @responses.activate
    def test_html_response_detected(self, jira):
        responses.add(responses.GET, "https://test.atlassian.net/rest/api/3/issue/TEST-1",
            body="<html><body>Login</body></html>", status=200, content_type="text/html")
        with pytest.raises(Exception):
            jira.get_card_title("TEST-1")

    @responses.activate
    def test_network_error(self, jira):
        responses.add(responses.GET, "https://test.atlassian.net/rest/api/3/issue/TEST-1",
            body=ConnectionError("Network error"))
        with pytest.raises(Exception):
            jira.get_card_title("TEST-1")
