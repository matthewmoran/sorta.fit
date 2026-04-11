"""Integration tests for Linear adapter -- port of linear-adapter-validation.bats"""
import pytest
import responses

from sortafit.adapters.linear import LinearAdapter
from sortafit.config import Config


@pytest.fixture
def linear_config(tmp_path):
    return Config(
        board_adapter="linear",
        board_domain="api.linear.app",
        board_project_key="TEAM",
        board_api_token="test-token",
        target_repo=str(tmp_path),
        sorta_root=str(tmp_path),
    )


@pytest.fixture
def linear(linear_config):
    return LinearAdapter(linear_config)


class TestLinearErrorHandling:
    @responses.activate
    def test_200_success(self, linear):
        responses.add(responses.POST, "https://api.linear.app/graphql",
            json={"data": {"issues": {"nodes": [{"title": "Test"}]}}}, status=200)
        node = linear._query_issue("TEAM-1", "title")
        assert node["title"] == "Test"

    @responses.activate
    def test_401_unauthorized(self, linear):
        responses.add(responses.POST, "https://api.linear.app/graphql",
            json={"error": "Unauthorized"}, status=401)
        with pytest.raises(Exception):
            linear._graphql("query { viewer { id } }")

    @responses.activate
    def test_500_server_error(self, linear):
        responses.add(responses.POST, "https://api.linear.app/graphql",
            json={"error": "Internal"}, status=500)
        with pytest.raises(Exception):
            linear._graphql("query { viewer { id } }")

    @responses.activate
    def test_html_response(self, linear):
        responses.add(responses.POST, "https://api.linear.app/graphql",
            body="<html>Error</html>", status=200, content_type="text/html")
        with pytest.raises(Exception):
            linear._graphql("query { viewer { id } }")

    @responses.activate
    def test_graphql_error(self, linear):
        responses.add(responses.POST, "https://api.linear.app/graphql",
            json={"errors": [{"message": "Query failed"}]}, status=200)
        with pytest.raises(RuntimeError, match="Query failed"):
            linear._graphql("query { viewer { id } }")

    @responses.activate
    def test_network_error(self, linear):
        responses.add(responses.POST, "https://api.linear.app/graphql",
            body=ConnectionError("Network error"))
        with pytest.raises(Exception):
            linear._graphql("query { viewer { id } }")
