"""Unit tests for render_template — port of tests/unit/render-template.bats"""
import pytest
from sortafit.utils import render_template


class TestRenderTemplate:
    def test_single_key(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("Hello {{NAME}}!")
        assert render_template(tmpl, NAME="World") == "Hello World!"

    def test_multiple_keys(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("{{GREETING}} {{NAME}}, welcome to {{PLACE}}.")
        result = render_template(tmpl, GREETING="Hello", NAME="Alice", PLACE="Wonderland")
        assert result == "Hello Alice, welcome to Wonderland."

    def test_missing_key_left_as_is(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("Hello {{NAME}}, your ID is {{UNKNOWN_KEY}}.")
        result = render_template(tmpl, NAME="Bob")
        assert result == "Hello Bob, your ID is {{UNKNOWN_KEY}}."

    def test_value_with_dollar_sign(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("Price: {{PRICE}}")
        assert render_template(tmpl, PRICE="$100") == "Price: $100"

    def test_value_with_backticks(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("Run: {{CMD}}")
        assert render_template(tmpl, CMD="`echo hello`") == "Run: `echo hello`"

    def test_value_with_single_quotes(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("Say: {{MSG}}")
        assert render_template(tmpl, MSG="it's working") == "Say: it's working"

    def test_value_with_double_quotes(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("Say: {{MSG}}")
        assert render_template(tmpl, MSG='She said "hello"') == 'Say: She said "hello"'

    def test_missing_template_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            render_template(tmp_path / "nonexistent.md", KEY="value")

    def test_empty_template(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("")
        assert render_template(tmpl, KEY="value") == ""

    def test_same_key_multiple_times(self, tmp_path):
        tmpl = tmp_path / "tmpl.md"
        tmpl.write_text("{{X}} and {{X}} again")
        assert render_template(tmpl, X="foo") == "foo and foo again"
