#!/usr/bin/env bats
# Integration tests for event logging — verifies event sequence from a mock runner cycle

TESTS_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
PROJECT_ROOT="$(cd "$TESTS_DIR/.." && pwd)"

load "${TESTS_DIR}/helpers/setup.sh"

setup() {
  setup_test_env
  source "$PROJECT_ROOT/core/utils.sh"
}

teardown() {
  teardown_test_env
}

@test "mock runner cycle produces expected event sequence" {
  export EVENT_LOGGING="on"
  export SORTA_ROOT="$TEST_TEMP_DIR"

  # Simulate cycle_started
  export CYCLE_ID="$$-$(date +%s)"
  export RUNNER_NAME="loop"
  log_event cycle_started

  # Simulate runner_started
  export RUNNER_NAME="refine"
  log_event runner_started

  # Simulate card_processed
  log_event card_processed card_key="TEST-1" outcome="success" runner="refine"

  # Simulate runner_completed
  log_event runner_completed cards_processed="1"

  # Simulate cycle_completed
  export RUNNER_NAME="loop"
  log_event cycle_completed duration_s="5"

  local event_file="$SORTA_ROOT/.sorta/events.jsonl"
  [[ -f "$event_file" ]]

  # Verify 5 events written
  local count
  count=$(wc -l < "$event_file")
  [[ "$count" -eq 5 ]]

  # Verify event sequence order and types
  run node -e "
    const fs = require('fs');
    const lines = fs.readFileSync(process.argv[1], 'utf8').trim().split('\n');
    const events = lines.map(l => JSON.parse(l));
    const expected = ['cycle_started', 'runner_started', 'card_processed', 'runner_completed', 'cycle_completed'];
    const actual = events.map(e => e.event);
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      console.error('Expected:', expected, 'Got:', actual);
      process.exit(1);
    }
    // Verify cycle_id present on all events
    const cycleId = events[0].cycle_id;
    if (!cycleId) { console.error('Missing cycle_id'); process.exit(2); }
    if (!events.every(e => e.cycle_id === cycleId)) {
      console.error('Inconsistent cycle_id');
      process.exit(3);
    }
    // Verify runner names
    if (events[0].runner !== 'loop') process.exit(4);
    if (events[1].runner !== 'refine') process.exit(5);
    if (events[4].runner !== 'loop') process.exit(6);
    // Verify card_processed data
    if (events[2].data.card_key !== 'TEST-1') process.exit(7);
    if (events[2].data.outcome !== 'success') process.exit(8);
    // Verify cycle_completed data
    if (events[4].data.duration_s !== '5') process.exit(9);
  " "$event_file"
  assert_success
}

@test "all events have valid JSON and required fields" {
  export EVENT_LOGGING="on"
  export SORTA_ROOT="$TEST_TEMP_DIR"
  export CYCLE_ID="test-cycle-123"
  export RUNNER_NAME="test"

  log_event cycle_started
  log_event runner_started
  log_event card_processed card_key="X-1" outcome="success" runner="test"
  log_event card_transitioned card_key="X-1" target_status="10070" transition_configured="true"
  log_event runner_completed cards_processed="1"
  log_event cycle_completed duration_s="10"

  local event_file="$SORTA_ROOT/.sorta/events.jsonl"

  run node -e "
    const fs = require('fs');
    const lines = fs.readFileSync(process.argv[1], 'utf8').trim().split('\n');
    lines.forEach((l, i) => {
      const e = JSON.parse(l);
      if (!e.timestamp) { console.error('Line', i, 'missing timestamp'); process.exit(1); }
      if (!e.event) { console.error('Line', i, 'missing event'); process.exit(2); }
      if (!e.runner) { console.error('Line', i, 'missing runner'); process.exit(3); }
      if (e.cycle_id !== 'test-cycle-123') { console.error('Line', i, 'wrong cycle_id'); process.exit(4); }
      if (isNaN(new Date(e.timestamp).getTime())) { console.error('Line', i, 'invalid timestamp'); process.exit(5); }
    });
  " "$event_file"
  assert_success
}
