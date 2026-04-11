"""Integration tests for event logging -- port of event-logging.bats"""
import json

from sortafit.config import Config
from sortafit.events import log_event


def _make_config(tmp_path):
    (tmp_path / ".sorta").mkdir(exist_ok=True)
    return Config(
        board_adapter="jira", board_domain="test.atlassian.net",
        board_project_key="TEST", target_repo=str(tmp_path),
        sorta_root=str(tmp_path), event_logging="on",
    )


class TestEventSequence:
    def test_full_cycle_sequence(self, tmp_path):
        config = _make_config(tmp_path)
        cycle_id = "test-123"
        log_event("cycle_started", config, runner_name="loop", cycle_id=cycle_id)
        log_event("runner_started", config, runner_name="refine", cycle_id=cycle_id)
        log_event("card_processed", config, runner_name="refine", cycle_id=cycle_id, card_key="TEST-1", outcome="success")
        log_event("runner_completed", config, runner_name="refine", cycle_id=cycle_id, cards_processed="1")
        log_event("cycle_completed", config, runner_name="loop", cycle_id=cycle_id)

        events_file = tmp_path / ".sorta" / "events.jsonl"
        lines = events_file.read_text().strip().split("\n")
        events = [json.loads(l) for l in lines]

        assert len(events) == 5
        assert events[0]["event"] == "cycle_started"
        assert events[-1]["event"] == "cycle_completed"
        # All share the same cycle_id
        assert all(e["cycle_id"] == cycle_id for e in events)

    def test_runner_name_propagation(self, tmp_path):
        config = _make_config(tmp_path)
        log_event("runner_started", config, runner_name="code")
        log_event("card_processed", config, runner_name="code", card_key="TEST-2")

        events_file = tmp_path / ".sorta" / "events.jsonl"
        lines = events_file.read_text().strip().split("\n")
        events = [json.loads(l) for l in lines]

        assert all(e["runner"] == "code" for e in events)
