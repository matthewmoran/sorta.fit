"""Unit tests for sortafit.claude — rate limit reset time parsing."""
import time

import pytest

from sortafit.claude import parse_rate_limit_reset


class TestParseRateLimitReset:
    """Tests for extracting reset time from Claude CLI rate limit messages."""

    def test_parses_pm_time_with_timezone(self):
        # Use a time guaranteed to be in the future (6 hours from now)
        from datetime import datetime
        future = datetime.now()
        future = future.replace(hour=(future.hour + 6) % 24, minute=0)
        hour_12 = future.hour % 12 or 12
        ampm = "pm" if future.hour >= 12 else "am"
        text = f"You've hit your limit \u00b7 resets {hour_12}{ampm} (America/Los_Angeles)"
        result = parse_rate_limit_reset(text)
        assert result is not None
        assert result > int(time.time())

    def test_parses_time_with_minutes(self):
        from datetime import datetime
        future = datetime.now()
        future = future.replace(hour=(future.hour + 3) % 24, minute=30)
        hour_12 = future.hour % 12 or 12
        ampm = "pm" if future.hour >= 12 else "am"
        text = f"resets {hour_12}:30{ampm} (America/New_York)"
        result = parse_rate_limit_reset(text)
        assert result is not None
        assert result > int(time.time())

    def test_parses_utc_timezone(self):
        from datetime import datetime, timezone as tz
        future = datetime.now(tz.utc)
        future = future.replace(hour=(future.hour + 4) % 24, minute=0)
        hour_12 = future.hour % 12 or 12
        ampm = "pm" if future.hour >= 12 else "am"
        text = f"resets {hour_12}{ampm} (UTC)"
        result = parse_rate_limit_reset(text)
        assert result is not None
        assert result > int(time.time())

    def test_returns_none_for_no_match(self):
        assert parse_rate_limit_reset("some random error") is None

    def test_returns_none_for_empty_string(self):
        assert parse_rate_limit_reset("") is None

    def test_result_is_reasonable_epoch(self):
        """Parsed result should be a reasonable Unix epoch (within 24h)."""
        from datetime import datetime
        future = datetime.now()
        future = future.replace(hour=(future.hour + 2) % 24, minute=0)
        hour_12 = future.hour % 12 or 12
        ampm = "pm" if future.hour >= 12 else "am"
        text = f"resets {hour_12}{ampm} (UTC)"
        result = parse_rate_limit_reset(text)
        assert result is not None
        now = int(time.time())
        # Should be in the future but within 24 hours
        assert result > now
        assert result < now + 86400

    def test_handles_12pm_noon(self):
        from datetime import datetime
        now = datetime.now()
        # If it's before noon, 12pm is in the future
        if now.hour < 12:
            text = "resets 12pm (UTC)"
            result = parse_rate_limit_reset(text)
            assert result is not None

    def test_handles_12am_midnight(self):
        from datetime import datetime
        now = datetime.now()
        # 12am is midnight — always "tomorrow" unless it's very early morning
        if now.hour > 1:
            text = "resets 12am (UTC)"
            result = parse_rate_limit_reset(text)
            assert result is not None
            assert result > int(time.time())
