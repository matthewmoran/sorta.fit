"""Integration tests for validate mode -- port of validate-mode.bats"""
import pytest
from sortafit.config import Config
from sortafit.loop import validate_runners
from sortafit.runners import RUNNER_REGISTRY


@pytest.fixture
def _clean_registries():
    """Snapshot and restore RUNNER_REGISTRY to prevent test pollution."""
    snapshot = dict(RUNNER_REGISTRY)
    yield
    RUNNER_REGISTRY.clear()
    RUNNER_REGISTRY.update(snapshot)


def _make_config(tmp_path, runners=None, adapter="jira"):
    (tmp_path / "adapters").mkdir(exist_ok=True)
    return Config(
        board_adapter=adapter,
        board_domain="test.atlassian.net",
        board_project_key="TEST",
        board_api_token="test-token",
        target_repo=str(tmp_path),
        sorta_root=str(tmp_path),
        runners_enabled=runners or ["refine", "code"],
        runner_refine_from="10000",
        runner_code_from="10069",
    )


class TestValidateMode:
    def test_valid_config_passes(self, tmp_path):
        config = _make_config(tmp_path)
        (tmp_path / "adapters" / "jira.config.sh").write_text("")
        with pytest.raises(SystemExit) as exc_info:
            validate_runners(config)
        assert exc_info.value.code == 0

    def test_unknown_runner_fails(self, tmp_path):
        config = _make_config(tmp_path, runners=["nonexistent"])
        (tmp_path / "adapters" / "jira.config.sh").write_text("")
        with pytest.raises(SystemExit) as exc_info:
            validate_runners(config)
        assert exc_info.value.code == 1

    def test_missing_adapter_config_fails(self, tmp_path):
        config = _make_config(tmp_path)
        # Remove the adapter config file created by _make_config
        adapter_cfg = tmp_path / "adapters" / "jira.config.sh"
        if adapter_cfg.exists():
            adapter_cfg.unlink()
        with pytest.raises(SystemExit) as exc_info:
            validate_runners(config)
        assert exc_info.value.code == 1

    def test_missing_from_status_warns_but_passes(self, tmp_path):
        config = _make_config(tmp_path)
        (tmp_path / "adapters" / "jira.config.sh").write_text("")
        config.runner_refine_from = ""  # Clear the FROM
        config.runner_code_from = ""
        with pytest.raises(SystemExit) as exc_info:
            validate_runners(config)
        assert exc_info.value.code == 0  # warns but passes

    def test_pro_registered_runner_passes_validation(
        self, tmp_path, _clean_registries
    ):
        from sortafit.runners.base import BaseRunner

        class ProRunner(BaseRunner):
            name = "pro_test"
            def process_card(self, issue_key):
                return "success"

        RUNNER_REGISTRY["pro_test"] = ProRunner

        config = _make_config(tmp_path, runners=["pro_test"])
        (tmp_path / "adapters" / "jira.config.sh").write_text("")
        with pytest.raises(SystemExit) as exc_info:
            validate_runners(config)
        assert exc_info.value.code == 0
