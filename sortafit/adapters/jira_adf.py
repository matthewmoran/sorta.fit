"""Jira Atlassian Document Format (ADF) converter.

Converts between ADF (Jira's rich text format) and Markdown.
Port of the inline Node.js functions in adapters/jira.sh.
"""
import json
import re


def adf_to_markdown(node: dict | None) -> str:
    """Convert a Jira ADF node tree to markdown text.

    Handles: doc, heading, paragraph, bulletList, orderedList, listItem,
    text, hardBreak. Matches the Node.js extractText() function exactly.
    """
    if not node:
        return ""

    node_type = node.get("type", "")

    if node_type == "text":
        return node.get("text", "")
    if node_type == "hardBreak":
        return "\n"

    content = node.get("content", [])
    if not content and node_type != "text":
        return ""

    if node_type == "doc":
        return "\n\n".join(adf_to_markdown(c) for c in content)

    if node_type == "heading":
        level = (node.get("attrs") or {}).get("level", 2)
        prefix = "#" * level
        text = "".join(adf_to_markdown(c) for c in content)
        return f"{prefix} {text}"

    if node_type in ("bulletList", "orderedList"):
        return "\n".join(adf_to_markdown(c) for c in content)

    if node_type == "listItem":
        text = "".join(adf_to_markdown(c) for c in content)
        return f"- {text}"

    # Default: concatenate children (paragraph, etc.)
    return "".join(adf_to_markdown(c) for c in content)


def markdown_to_adf(markdown: str) -> dict:
    """Convert markdown text to a Jira ADF document.

    Handles: headings (## / ###), bullet lists (- item), checklist items (- [ ] / - [x]),
    blank lines, and plain paragraphs.
    Port of the Node.js converter in jira.sh board_update_description().
    """
    lines = markdown.split("\n")
    content: list[dict] = []
    list_items: list[str] = []

    def flush_list():
        nonlocal list_items
        if list_items:
            content.append({
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
                        ],
                    }
                    for text in list_items
                ],
            })
            list_items = []

    for line in lines:
        if line.startswith("## "):
            flush_list()
            content.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": line[3:]}],
            })
        elif line.startswith("### "):
            flush_list()
            content.append({
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": line[4:]}],
            })
        elif re.match(r"^- \[[ x]\] ", line):
            list_items.append(re.sub(r"^- \[[ x]\] ", "", line))
        elif line.startswith("- "):
            list_items.append(line[2:])
        elif line.strip() == "":
            flush_list()
        else:
            flush_list()
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            })

    flush_list()
    if not content:
        content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": " "}],
        })

    return {"type": "doc", "version": 1, "content": content}
