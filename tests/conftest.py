"""Shared test fixtures for Sorta.Fit tests."""
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def test_env(tmp_path):
    """Create an isolated test environment with standard directory structure."""
    sorta_root = tmp_path / "sorta"
    sorta_root.mkdir()
    (sorta_root / "core").mkdir()
    (sorta_root / "adapters").mkdir()
    (sorta_root / "runners").mkdir()
    (sorta_root / "prompts").mkdir()
    (sorta_root / ".sorta").mkdir()
    return sorta_root


@pytest.fixture
def valid_env_file(test_env):
    """Write a minimal valid .env file and return the sorta_root path."""
    env_content = (
        'BOARD_ADAPTER=jira\n'
        'BOARD_DOMAIN=test.atlassian.net\n'
        'BOARD_API_TOKEN=test-token-do-not-use\n'
        'BOARD_PROJECT_KEY=TEST\n'
        'BOARD_EMAIL=test@example.com\n'
    )
    (test_env / ".env").write_text(env_content)
    return test_env


@pytest.fixture
def test_git_repo(tmp_path):
    """Create a minimal git repository for testing."""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo, check=True
    )
    (repo / ".gitkeep").touch()
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "init"], cwd=repo, check=True
    )
    return repo
