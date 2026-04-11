"""Unit tests for sortafit.events — port of log_event tests from utils.bats"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from sortafit.config import Config
from sortafit.events import log_event


def _make_config(tmp_path, event_logging="on"):
    (tmp_path / ".sorta").mkdir(exist_ok=True)
    return Config(
        board_adapter="jira", board_domain="test.atlassian.net",
        board_project_key="TEST", target_repo=str(tmp_path),
        sorta_root=str(tmp_path), event_logging=event_logging,
    )


class TestLogEvent:
    def test_creates_sorta_dir(self, tmp_path):
        sorta_dir = tmp_path / ".sorta"
        if sorta_dir.exists():
            import shutil
            shutil.rmtree(sorta_dir)
        config = Config(
            board_adapter="jira", board_domain="test.atlassian.net",
            board_project_key="TEST", target_repo=str(tmp_path),
            sorta_root=str(tmp_path), event_logging="on",
        )
        log_event("test_event", config, runner_name="test")
        assert sorta_dir.is_dir()

    def test_writes_valid_json(self, tmp_path):
        config = _make_config(tmp_path)
        log_event("test_event", config, runner_name="test")
        line = (tmp_path / ".sorta" / "events.jsonl").read_text().strip()
        event = json.loads(line)
        assert "timestamp" in event

    def test_required_fields(self, tmp_path):
        config = _make_config(tmp_path)
        log_event("my_event", config, runner_name="test-runner")
        line = (tmp_path / ".sorta" / "events.jsonl").read_text().strip()
        event = json.loads(line)
        assert event["event"] == "my_event"
        assert event["runner"] == "test-runner"
        assert "timestamp" in event

    def test_iso8601_timestamp(self, tmp_path):
        config = _make_config(tmp_path)
        log_event("ts_event", config, runner_name="test")
        line = (tmp_path / ".sorta" / "events.jsonl").read_text().strip()
        event = json.loads(line)
        # Should parse as ISO format
        datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))

    def test_appends_not_overwrites(self, tmp_path):
        config = _make_config(tmp_path)
        log_event("event_one", config, runner_name="test")
        log_event("event_two", config, runner_name="test")
        lines = (tmp_path / ".sorta" / "events.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2

    def test_includes_data_fields(self, tmp_path):
        config = _make_config(tmp_path)
        log_event("card_processed", config, runner_name="test", card_key="SF-1", outcome="success")
        line = (tmp_path / ".sorta" / "events.jsonl").read_text().strip()
        event = json.loads(line)
        assert event["data"]["card_key"] == "SF-1"
        assert event["data"]["outcome"] == "success"

    def test_no_output(self, tmp_path, capsys):
        config = _make_config(tmp_path)
        log_event("silent_event", config, runner_name="test")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_failure_does_not_raise(self, tmp_path):
        config = Config(
            board_adapter="jira", board_domain="test.atlassian.net",
            board_project_key="TEST", target_repo=str(tmp_path),
            sorta_root="/nonexistent/readonly/path", event_logging="on",
        )
        # Should not raise
        log_event("should_not_crash", config, runner_name="test")

    def test_noop_when_logging_off(self, tmp_path):
        config = _make_config(tmp_path, event_logging="off")
        log_event("should_not_write", config, runner_name="test")
        events_file = tmp_path / ".sorta" / "events.jsonl"
        assert not events_file.exists()

    def test_includes_cycle_id(self, tmp_path):
        config = _make_config(tmp_path)
        log_event("cycle_event", config, runner_name="test", cycle_id="12345-1680000000")
        line = (tmp_path / ".sorta" / "events.jsonl").read_text().strip()
        event = json.loads(line)
        assert event["cycle_id"] == "12345-1680000000"
