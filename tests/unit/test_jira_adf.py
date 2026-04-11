"""Unit tests for sortafit.adapters.jira_adf — ADF conversion (previously untested)"""
from sortafit.adapters.jira_adf import adf_to_markdown, markdown_to_adf


class TestAdfToMarkdown:
    def test_plain_text(self):
        doc = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}
        ]}
        assert adf_to_markdown(doc) == "Hello world"

    def test_heading(self):
        doc = {"type": "doc", "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Title"}]}
        ]}
        assert adf_to_markdown(doc) == "## Title"

    def test_bullet_list(self):
        doc = {"type": "doc", "content": [
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [{"type": "text", "text": "item one"}]},
                {"type": "listItem", "content": [{"type": "text", "text": "item two"}]},
            ]}
        ]}
        result = adf_to_markdown(doc)
        assert "- item one" in result
        assert "- item two" in result

    def test_hard_break(self):
        doc = {"type": "paragraph", "content": [
            {"type": "text", "text": "line1"},
            {"type": "hardBreak"},
            {"type": "text", "text": "line2"},
        ]}
        assert adf_to_markdown(doc) == "line1\nline2"

    def test_none_input(self):
        assert adf_to_markdown(None) == ""

    def test_empty_doc(self):
        assert adf_to_markdown({"type": "doc", "content": []}) == ""


class TestMarkdownToAdf:
    def test_plain_paragraph(self):
        result = markdown_to_adf("Hello world")
        assert result["type"] == "doc"
        assert result["version"] == 1
        assert result["content"][0]["type"] == "paragraph"
        assert result["content"][0]["content"][0]["text"] == "Hello world"

    def test_heading(self):
        result = markdown_to_adf("## My Title")
        assert result["content"][0]["type"] == "heading"
        assert result["content"][0]["attrs"]["level"] == 2

    def test_bullet_list(self):
        result = markdown_to_adf("- item one\n- item two")
        assert result["content"][0]["type"] == "bulletList"
        items = result["content"][0]["content"]
        assert len(items) == 2

    def test_empty_produces_space(self):
        result = markdown_to_adf("")
        assert result["content"][0]["content"][0]["text"] == " "

    def test_checklist_item(self):
        result = markdown_to_adf("- [ ] unchecked\n- [x] checked")
        items = result["content"][0]["content"]
        assert items[0]["content"][0]["content"][0]["text"] == "unchecked"
        assert items[1]["content"][0]["content"][0]["text"] == "checked"
