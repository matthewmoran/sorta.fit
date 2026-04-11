"""Unit tests for sortafit.utils — port of tests/unit/utils.bats"""
import json
import os
import time
from pathlib import Path

import pytest

from sortafit.utils import (
    extract_pr_url,
    is_rate_limited,
    lock_acquire,
    lock_release,
    matches_type_filter,
    require_command,
    set_rate_limited,
    slugify,
)


class TestSlugify:
    def test_uppercase_to_lowercase(self):
        assert slugify("HELLO WORLD") == "hello-world"

    def test_spaces_to_dashes(self):
        assert slugify("hello world") == "hello-world"

    def test_removes_special_chars(self):
        assert slugify("hello@world!foo") == "hello-world-foo"

    def test_collapses_consecutive_dashes(self):
        assert slugify("hello---world") == "hello-world"

    def test_strips_leading_dashes(self):
        assert slugify("---hello") == "hello"

    def test_strips_trailing_dashes(self):
        assert slugify("hello---") == "hello"

    def test_truncates_to_40_chars(self):
        result = slugify("this is a very long string that should be truncated to forty characters maximum")
        assert len(result) <= 40

    def test_empty_input(self):
        assert slugify("") == ""

    def test_mixed_case_and_special(self):
        assert slugify("SF-16 Add Tests & Validations!") == "sf-16-add-tests-validations"


class TestMatchesTypeFilter:
    def test_empty_filter_matches_all(self):
        assert matches_type_filter("Bug", "") is True

    def test_exact_match(self):
        assert matches_type_filter("Bug", "Bug") is True

    def test_no_match(self):
        assert matches_type_filter("Story", "Bug") is False

    def test_multiple_types_match(self):
        assert matches_type_filter("Bug", "Story,Bug,Task") is True

    def test_multiple_types_no_match(self):
        assert matches_type_filter("Epic", "Story,Bug,Task") is False

    def test_whitespace_trimmed(self):
        assert matches_type_filter("Bug", "Story , Bug , Task") is True


class TestExtractPrUrl:
    def test_single_url(self):
        assert extract_pr_url("PR opened at https://github.com/owner/repo/pull/123") == "https://github.com/owner/repo/pull/123"

    def test_multiple_urls_returns_last(self):
        text = "First PR: https://github.com/owner/repo/pull/1\nSecond PR: https://github.com/owner/repo/pull/42"
        assert extract_pr_url(text, last=True) == "https://github.com/owner/repo/pull/42"

    def test_no_url(self):
        assert extract_pr_url("no links here") == ""

    def test_url_in_surrounding_text(self):
        assert extract_pr_url("See https://github.com/org/project/pull/99 for details") == "https://github.com/org/project/pull/99"

    def test_first_mode(self):
        text = "First: https://github.com/owner/repo/pull/1\nSecond: https://github.com/owner/repo/pull/2"
        assert extract_pr_url(text, last=False) == "https://github.com/owner/repo/pull/1"


class TestRequireCommand:
    def test_existing_command(self):
        assert require_command("git") is True

    def test_missing_command(self):
        assert require_command("nonexistent_command_12345") is False


class TestLock:
    def test_fresh_acquire(self, tmp_path):
        lock_dir = tmp_path / ".test.lock"
        assert lock_acquire(lock_dir) is True
        assert lock_dir.is_dir()
        lock_release(lock_dir)

    def test_double_acquire_fails(self, tmp_path):
        lock_dir = tmp_path / ".test.lock"
        assert lock_acquire(lock_dir) is True
        assert lock_acquire(lock_dir) is False
        lock_release(lock_dir)

    def test_release_then_reacquire(self, tmp_path):
        lock_dir = tmp_path / ".test.lock"
        assert lock_acquire(lock_dir) is True
        lock_release(lock_dir)
        assert lock_acquire(lock_dir) is True
        lock_release(lock_dir)

    def test_stale_lock_cleaned(self, tmp_path):
        lock_dir = tmp_path / ".test.lock"
        lock_dir.mkdir()
        (lock_dir / "pid").write_text("999999")
        # Verify that PID doesn't exist
        try:
            os.kill(999999, 0)
            pytest.skip("PID 999999 unexpectedly alive")
        except OSError:
            pass
        assert lock_acquire(lock_dir) is True
        lock_release(lock_dir)


class TestRateLimited:
    def test_no_file_not_limited(self, tmp_path):
        assert is_rate_limited(str(tmp_path)) is False

    def test_future_reset_is_limited(self, tmp_path):
        rate_file = tmp_path / ".rate-limited"
        rate_file.write_text(str(int(time.time()) + 1800))
        assert is_rate_limited(str(tmp_path)) is True

    def test_past_reset_not_limited(self, tmp_path):
        rate_file = tmp_path / ".rate-limited"
        rate_file.write_text(str(int(time.time()) - 60))
        assert is_rate_limited(str(tmp_path)) is False
        assert not rate_file.exists()

    def test_set_rate_limited_with_reset_epoch(self, tmp_path):
        from sortafit.utils import set_rate_limited
        reset_epoch = int(time.time()) + 3600
        set_rate_limited(str(tmp_path), reset_epoch)
        rate_file = tmp_path / ".rate-limited"
        assert rate_file.exists()
        assert int(rate_file.read_text().strip()) == reset_epoch

    def test_set_rate_limited_default_fallback(self, tmp_path):
        from sortafit.utils import set_rate_limited
        set_rate_limited(str(tmp_path))
        rate_file = tmp_path / ".rate-limited"
        stored = int(rate_file.read_text().strip())
        # Default should be ~30 min from now
        assert stored > int(time.time()) + 1700
        assert stored < int(time.time()) + 1900

    def test_remaining_seconds_in_log(self, tmp_path, capsys):
        rate_file = tmp_path / ".rate-limited"
        rate_file.write_text(str(int(time.time()) + 600))
        is_rate_limited(str(tmp_path))
        captured = capsys.readouterr()
        assert "remaining" in captured.err.lower()
