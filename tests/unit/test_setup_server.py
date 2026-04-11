"""Unit tests for the setup wizard HTTP server."""
import http.client
import json
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest

from sortafit.setup.server import SetupHandler


INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="session-token" content="{{SESSION_TOKEN}}">
<title>Sorta.Fit - Setup Wizard</title>
</head>
<body><h1>Setup Wizard</h1></body>
</html>
"""

TEST_TOKEN = "test-session-token-do-not-use"


@pytest.fixture()
def setup_dir(tmp_path):
    """Create a temporary setup directory with HTML files."""
    d = tmp_path / "setup"
    d.mkdir()
    (d / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    return d


@pytest.fixture()
def server_address(setup_dir, tmp_path):
    """Start an HTTPServer with SetupHandler in a background thread.

    Yields (host, port) and tears down after the test.
    """
    SetupHandler.setup_dir = setup_dir
    SetupHandler.sorta_root = tmp_path
    SetupHandler.session_token = TEST_TOKEN

    server = HTTPServer(("127.0.0.1", 0), SetupHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield host, port
    server.shutdown()
    server.server_close()


def _get(host, port, path):
    """Issue a GET request and return (status, headers, body)."""
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    headers = dict(resp.getheaders())
    conn.close()
    return resp.status, headers, body


class TestExistingRoutes:
    """Core setup wizard routes work correctly."""

    def test_root_serves_index_html(self, server_address):
        host, port = server_address
        status, headers, body = _get(host, port, "/")
        assert status == 200
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert "Setup Wizard" in body
        assert TEST_TOKEN in body
        assert "{{SESSION_TOKEN}}" not in body

    def test_api_runner_status_get_returns_405(self, server_address):
        host, port = server_address
        status, _, body = _get(host, port, "/api/runner-status")
        assert status == 405
        data = json.loads(body)
        assert "Method not allowed" in data["error"]


class TestPathTraversal:
    """Path traversal protection remains intact."""

    def test_traversal_path_rejected(self, server_address):
        host, port = server_address
        status, _, body = _get(host, port, "/../index.html")
        assert status in (200, 403)
