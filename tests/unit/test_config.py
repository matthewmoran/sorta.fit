"""Unit tests for sortafit.config — port of tests/unit/config.bats"""
import pytest
from sortafit.config import Config, ConfigError, load_config, parse_env_file


def _write_valid_env(sorta_root, target_repo):
    """Write a minimal valid .env file."""
    env = sorta_root / ".env"
    env.write_text(
        f'BOARD_ADAPTER=jira\n'
        f'BOARD_DOMAIN=test.atlassian.net\n'
        f'BOARD_API_TOKEN=test-token-do-not-use\n'
        f'BOARD_PROJECT_KEY=TEST\n'
        f'BOARD_EMAIL=test@example.com\n'
        f'TARGET_REPO={target_repo}\n'
    )
    # Create adapter config
    (sorta_root / "adapters").mkdir(exist_ok=True)
    (sorta_root / "adapters" / "jira.config.sh").write_text("")
    return env


class TestParseEnvFile:
    def test_basic_key_value(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("KEY=value\n")
        assert parse_env_file(f) == {"KEY": "value"}

    def test_strips_quotes(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text('KEY="quoted value"\n')
        assert parse_env_file(f) == {"KEY": "quoted value"}

    def test_skips_comments_and_blanks(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("# comment\n\nKEY=val\n")
        assert parse_env_file(f) == {"KEY": "val"}


class TestLoadConfig:
    def test_valid_config_loads(self, test_env, test_git_repo):
        _write_valid_env(test_env, str(test_git_repo))
        config = load_config(test_env / ".env", test_env)
        assert config.board_adapter == "jira"
        assert config.board_domain == "test.atlassian.net"

    def test_missing_board_adapter(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text().replace("BOARD_ADAPTER=jira\n", "")
        env.write_text(text)
        with pytest.raises(ConfigError, match="BOARD_ADAPTER"):
            load_config(env, test_env)

    def test_invalid_board_adapter(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text().replace("BOARD_ADAPTER=jira", "BOARD_ADAPTER=dropbox")
        env.write_text(text)
        with pytest.raises(ConfigError, match="Unknown adapter"):
            load_config(env, test_env)

    def test_domain_with_protocol_fails(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text().replace("BOARD_DOMAIN=test.atlassian.net", "BOARD_DOMAIN=https://foo.atlassian.net")
        env.write_text(text)
        with pytest.raises(ConfigError, match="Invalid BOARD_DOMAIN"):
            load_config(env, test_env)

    def test_domain_with_trailing_slash_fails(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text().replace("BOARD_DOMAIN=test.atlassian.net", "BOARD_DOMAIN=foo.atlassian.net/")
        env.write_text(text)
        with pytest.raises(ConfigError, match="Invalid BOARD_DOMAIN"):
            load_config(env, test_env)

    def test_domain_single_char_fails(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text().replace("BOARD_DOMAIN=test.atlassian.net", "BOARD_DOMAIN=x")
        env.write_text(text)
        with pytest.raises(ConfigError, match="Invalid BOARD_DOMAIN"):
            load_config(env, test_env)

    def test_missing_board_api_token(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text().replace("BOARD_API_TOKEN=test-token-do-not-use\n", "")
        env.write_text(text)
        with pytest.raises(ConfigError, match="BOARD_API_TOKEN"):
            load_config(env, test_env)

    def test_missing_board_project_key(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text().replace("BOARD_PROJECT_KEY=TEST\n", "")
        env.write_text(text)
        with pytest.raises(ConfigError, match="BOARD_PROJECT_KEY"):
            load_config(env, test_env)

    def test_target_repo_relative_path_fails(self, test_env):
        env = _write_valid_env(test_env, "./repo")
        with pytest.raises(ConfigError, match="absolute path"):
            load_config(env, test_env)

    def test_target_repo_nonexistent_fails(self, test_env, tmp_path):
        # Use an absolute path that doesn't exist (works on both Unix and Windows)
        nonexistent = str(tmp_path / "nonexistent" / "path" / "to" / "repo")
        env = _write_valid_env(test_env, nonexistent)
        with pytest.raises(ConfigError, match="does not exist"):
            load_config(env, test_env)

    def test_target_repo_non_git_fails(self, test_env, tmp_path):
        non_git = tmp_path / "not-a-repo"
        non_git.mkdir()
        env = _write_valid_env(test_env, str(non_git))
        with pytest.raises(ConfigError, match="not a git repository"):
            load_config(env, test_env)

    def test_valid_adapter_names(self, test_env, test_git_repo):
        for adapter in ["jira", "linear", "github-issues"]:
            env = _write_valid_env(test_env, str(test_git_repo))
            text = env.read_text().replace("BOARD_ADAPTER=jira", f"BOARD_ADAPTER={adapter}")
            env.write_text(text)
            (test_env / "adapters" / f"{adapter}.config.sh").write_text("")
            config = load_config(env, test_env)
            assert config.board_adapter == adapter

    def test_github_issues_empty_token_succeeds(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text()
        text = text.replace("BOARD_ADAPTER=jira", "BOARD_ADAPTER=github-issues")
        text = text.replace("BOARD_DOMAIN=test.atlassian.net", "BOARD_DOMAIN=github.com")
        text = text.replace("BOARD_API_TOKEN=test-token-do-not-use\n", "")
        env.write_text(text)
        (test_env / "adapters" / "github-issues.config.sh").write_text("")
        config = load_config(env, test_env)
        assert config.board_adapter == "github-issues"

    def test_linear_empty_token_fails(self, test_env, test_git_repo):
        env = _write_valid_env(test_env, str(test_git_repo))
        text = env.read_text()
        text = text.replace("BOARD_ADAPTER=jira", "BOARD_ADAPTER=linear")
        text = text.replace("BOARD_DOMAIN=test.atlassian.net", "BOARD_DOMAIN=api.linear.app")
        text = text.replace("BOARD_API_TOKEN=test-token-do-not-use\n", "")
        env.write_text(text)
        (test_env / "adapters" / "linear.config.sh").write_text("")
        with pytest.raises(ConfigError, match="BOARD_API_TOKEN"):
            load_config(env, test_env)

