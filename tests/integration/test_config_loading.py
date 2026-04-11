"""Integration tests for config loading defaults -- port of config-loading.bats"""
import pytest
from sortafit.config import load_config


def _write_env(sorta_root, target_repo, extras=""):
    env = sorta_root / ".env"
    env.write_text(
        f'BOARD_ADAPTER=jira\n'
        f'BOARD_DOMAIN=test.atlassian.net\n'
        f'BOARD_API_TOKEN=test-token\n'
        f'BOARD_PROJECT_KEY=TEST\n'
        f'BOARD_EMAIL=test@example.com\n'
        f'TARGET_REPO={target_repo}\n'
        f'{extras}'
    )
    (sorta_root / "adapters").mkdir(exist_ok=True)
    (sorta_root / "adapters" / "jira.config.sh").write_text("")
    return env


class TestConfigDefaults:
    def test_default_git_base_branch(self, test_env, test_git_repo):
        _write_env(test_env, str(test_git_repo))
        config = load_config(test_env / ".env", test_env)
        assert config.git_base_branch == "main"

    def test_default_poll_interval(self, test_env, test_git_repo):
        _write_env(test_env, str(test_git_repo))
        config = load_config(test_env / ".env", test_env)
        assert config.poll_interval == 3600

    def test_default_runners_enabled(self, test_env, test_git_repo):
        _write_env(test_env, str(test_git_repo))
        config = load_config(test_env / ".env", test_env)
        assert config.runners_enabled == ["refine", "code"]

    def test_custom_values_override(self, test_env, test_git_repo):
        _write_env(test_env, str(test_git_repo),
                   "GIT_BASE_BRANCH=develop\nPOLL_INTERVAL=600\nRUNNERS_ENABLED=review,merge\n")
        config = load_config(test_env / ".env", test_env)
        assert config.git_base_branch == "develop"
        assert config.poll_interval == 600
        assert config.runners_enabled == ["review", "merge"]
