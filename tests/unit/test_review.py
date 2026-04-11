"""Unit tests for review runner diff preparation logic."""
import textwrap

import pytest

from sortafit.runners.review import NOISE_PATTERNS, parse_diff_files, prepare_diff


def _make_file_diff(filename: str, content_lines: int = 5) -> str:
    """Build a fake unified diff chunk for one file."""
    lines = "\n".join(f"+line {i}" for i in range(content_lines))
    return (
        f"diff --git a/{filename} b/{filename}\n"
        f"index abc1234..def5678 100644\n"
        f"--- a/{filename}\n"
        f"+++ b/{filename}\n"
        f"@@ -0,0 +1,{content_lines} @@\n"
        f"{lines}\n"
    )


class TestParseDiffFiles:
    """Tests for splitting a raw diff into per-file chunks."""

    def test_single_file(self):
        raw = _make_file_diff("src/main.py")
        files = parse_diff_files(raw)
        assert len(files) == 1
        assert files[0][0] == "src/main.py"
        assert "diff --git" in files[0][1]

    def test_multiple_files(self):
        raw = _make_file_diff("a.py") + _make_file_diff("b.py") + _make_file_diff("c.py")
        files = parse_diff_files(raw)
        assert len(files) == 3
        assert [f[0] for f in files] == ["a.py", "b.py", "c.py"]

    def test_empty_diff(self):
        assert parse_diff_files("") == []

    def test_preserves_full_chunk(self):
        raw = _make_file_diff("file.py", content_lines=10)
        files = parse_diff_files(raw)
        assert files[0][1] == raw

    def test_binary_file_diff(self):
        raw = (
            "diff --git a/image.png b/image.png\n"
            "new file mode 100644\n"
            "index 0000000..abc1234\n"
            "Binary files /dev/null and b/image.png differ\n"
        )
        files = parse_diff_files(raw)
        assert len(files) == 1
        assert files[0][0] == "image.png"


class TestNoisePatterns:
    """Verify the noise pattern list catches expected files."""

    def test_lock_files_are_noise(self):
        noise_names = [
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "Pipfile.lock",
            "poetry.lock",
            "Cargo.lock",
            "go.sum",
            "composer.lock",
        ]
        for name in noise_names:
            assert any(
                _matches_noise(name, pat) for pat in NOISE_PATTERNS
            ), f"{name} should be noise"

    def test_source_maps_are_noise(self):
        assert any(_matches_noise("bundle.js.map", pat) for pat in NOISE_PATTERNS)
        assert any(_matches_noise("styles.css.map", pat) for pat in NOISE_PATTERNS)

    def test_minified_files_are_noise(self):
        assert any(_matches_noise("app.min.js", pat) for pat in NOISE_PATTERNS)
        assert any(_matches_noise("styles.min.css", pat) for pat in NOISE_PATTERNS)

    def test_normal_source_not_noise(self):
        normal = ["src/main.py", "lib/utils.ts", "README.md", "package.json"]
        for name in normal:
            assert not any(
                _matches_noise(name, pat) for pat in NOISE_PATTERNS
            ), f"{name} should NOT be noise"


def _matches_noise(filename: str, pattern: str) -> bool:
    """Check if a filename matches a noise pattern (same logic as prepare_diff)."""
    from fnmatch import fnmatch
    basename = filename.rsplit("/", 1)[-1] if "/" in filename else filename
    return fnmatch(basename, pattern)


class TestPrepareDiff:
    """Tests for the full prepare_diff pipeline."""

    def test_small_diff_passes_through(self):
        raw = _make_file_diff("main.py", 5)
        result = prepare_diff(raw, max_chars=100000)
        assert result == raw

    def test_noise_files_filtered(self):
        signal = _make_file_diff("src/app.py", 5)
        noise = _make_file_diff("package-lock.json", 100)
        raw = signal + noise
        result = prepare_diff(raw, max_chars=100000)
        assert "app.py" in result
        # Noise file diff body should not appear, but name appears in the summary
        assert "diff --git a/package-lock.json" not in result
        assert "filtered out" in result.lower() or "noise" in result.lower()

    def test_noise_filter_logs_what_was_dropped(self):
        signal = _make_file_diff("src/app.py", 5)
        noise = _make_file_diff("yarn.lock", 100)
        raw = signal + noise
        result = prepare_diff(raw, max_chars=100000)
        assert "yarn.lock" in result  # mentioned in the summary

    def test_smart_truncate_drops_whole_files(self):
        # Create a diff where 3 files total ~300 chars each, limit is 700
        file_a = _make_file_diff("a.py", 20)
        file_b = _make_file_diff("b.py", 20)
        file_c = _make_file_diff("c.py", 20)
        raw = file_a + file_b + file_c
        total = len(raw)

        # Set limit so only 2 files fit
        limit = len(file_a) + len(file_b) + 100  # room for summary
        result = prepare_diff(raw, max_chars=limit)

        assert "a.py" in result
        assert "b.py" in result
        # c.py should be dropped, not truncated mid-file
        assert "+line 0" not in result.split("c.py")[-1] if "c.py" in result else True
        assert "omitted" in result.lower() or "truncated" in result.lower()

    def test_truncation_summary_lists_dropped_files(self):
        file_a = _make_file_diff("a.py", 5)
        file_b = _make_file_diff("b.py", 5)
        file_c = _make_file_diff("dropped.py", 5)
        raw = file_a + file_b + file_c
        limit = len(file_a) + len(file_b) + 100
        result = prepare_diff(raw, max_chars=limit)
        assert "dropped.py" in result

    def test_combined_noise_filter_and_truncation(self):
        signal_a = _make_file_diff("src/core.py", 10)
        signal_b = _make_file_diff("src/utils.py", 10)
        signal_c = _make_file_diff("src/extra.py", 10)
        noise = _make_file_diff("package-lock.json", 500)
        raw = signal_a + noise + signal_b + signal_c

        # Limit that fits signal_a + signal_b but not signal_c
        limit = len(signal_a) + len(signal_b) + 150
        result = prepare_diff(raw, max_chars=limit)

        assert "core.py" in result
        assert "utils.py" in result
        assert "package-lock.json" not in result.split("\n\n---")[0]  # not in diff body

    def test_all_noise_returns_empty_with_summary(self):
        raw = _make_file_diff("package-lock.json", 50) + _make_file_diff("yarn.lock", 50)
        result = prepare_diff(raw, max_chars=100000)
        assert "no reviewable" in result.lower() or "filtered" in result.lower()

    def test_respects_max_chars_limit(self):
        # Even after filtering and truncation, result must be under limit
        files = [_make_file_diff(f"file_{i}.py", 50) for i in range(20)]
        raw = "".join(files)
        limit = 5000
        result = prepare_diff(raw, max_chars=limit)
        assert len(result) <= limit

    def test_single_huge_file_truncated_with_note(self):
        # One file bigger than the entire limit — can't include it whole
        huge = _make_file_diff("huge.py", 2000)
        limit = 500
        result = prepare_diff(huge, max_chars=limit)
        assert len(result) <= limit
        assert "huge.py" in result
