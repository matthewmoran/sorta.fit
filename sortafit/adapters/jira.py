"""Sorta.Fit Jira Cloud adapter — port of adapters/jira.sh"""
import base64
import json
import re

import requests

from sortafit.adapters.base import BoardAdapter
from sortafit.adapters.jira_adf import adf_to_markdown, markdown_to_adf
from sortafit.config import Config
from sortafit.utils import log_error


class JiraAdapter(BoardAdapter):
    """Jira Cloud REST API v3 adapter."""

    def __init__(self, config: Config):
        self.config = config
        self.base_url = f"https://{config.board_domain}/rest/api/3"
        credentials = f"{config.board_email}:{config.board_api_token}"
        auth_b64 = base64.b64encode(credentials.encode()).decode()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make a Jira API request with validation. Port of jira_curl()."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.RequestException as e:
            log_error(f"Jira API request failed (network error): {e}")
            raise

        body = resp.text
        if resp.status_code >= 400 or (body and body[0] == "<"):
            log_error(f"Jira API error (HTTP {resp.status_code})")
            if body and body[0] == "<":
                log_error("Received HTML instead of JSON — check BOARD_DOMAIN, BOARD_EMAIL, and BOARD_API_TOKEN in .env")
            else:
                log_error(f"Response: {body[:200]}")
            raise requests.HTTPError(f"Jira API error (HTTP {resp.status_code})", response=resp)

        if not body:
            return {}
        return resp.json()

    def get_cards_in_status(self, status: str, max_count: int = 10, start_at: int = 0) -> list[str]:
        if not status:
            log_error("No status ID configured for this runner. Check RUNNER_*_FROM in .env.")
            return []
        data = self._request("POST", f"search/jql?startAt={start_at}", json={
            "jql": f"project={self.config.board_project_key} AND status={status} ORDER BY rank ASC",
            "maxResults": max_count,
        })
        return [str(issue["id"]) for issue in data.get("issues", [])]

    def get_card_key(self, issue_id: str) -> str:
        data = self._request("GET", f"issue/{issue_id}")
        return data["key"]

    def get_card_title(self, issue_key: str) -> str:
        data = self._request("GET", f"issue/{issue_key}")
        return data["fields"]["summary"]

    def get_card_type(self, issue_key: str) -> str:
        data = self._request("GET", f"issue/{issue_key}")
        return data["fields"]["issuetype"]["name"]

    def get_card_description(self, issue_key: str) -> str:
        data = self._request("GET", f"issue/{issue_key}")
        desc = data["fields"].get("description")
        if not desc:
            return ""
        return adf_to_markdown(desc)

    def get_card_comments(self, issue_key: str) -> str:
        data = self._request("GET", f"issue/{issue_key}/comment")
        comments = data.get("comments", [])
        if not comments:
            return "No comments"
        parts = []
        for c in comments:
            parts.append("---")
            author = c.get("author", {}).get("displayName", "Unknown")
            parts.append(f"Author: {author}")
            parts.append(f"Date: {c.get('created', '')}")
            body_text = adf_to_markdown(c.get("body"))
            parts.append(body_text)
        return "\n".join(parts)

    def get_card_summary(self, issue_key: str) -> str:
        data = self._request("GET", f"issue/{issue_key}")
        fields = data["fields"]
        return (
            f"Key: {data['key']}\n"
            f"Summary: {fields['summary']}\n"
            f"Status: {fields['status']['name']}\n"
            f"Type: {fields['issuetype']['name']}\n"
            f"Priority: {(fields.get('priority') or {}).get('name', 'None')}"
        )

    def update_description(self, issue_key: str, markdown: str) -> None:
        adf_doc = markdown_to_adf(markdown)
        self._request("PUT", f"issue/{issue_key}", json={
            "fields": {"description": adf_doc}
        })

    def add_comment(self, issue_key: str, comment: str) -> None:
        self._request("POST", f"issue/{issue_key}/comment", json={
            "body": {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}]
            }
        })

    def transition(self, issue_key: str, transition_id: str) -> None:
        self._request("POST", f"issue/{issue_key}/transitions", json={
            "transition": {"id": transition_id}
        })

    def get_card_status(self, issue_key: str) -> str:
        data = self._request("GET", f"issue/{issue_key}?fields=status")
        status = data.get("fields", {}).get("status")
        if status:
            return f"{status['name']}|{status['id']}"
        return ""

    def get_card_links(self, issue_key: str) -> str:
        data = self._request("GET", f"issue/{issue_key}?fields=issuelinks,parent,subtasks,labels")
        fields = data.get("fields", {})
        lines = []

        # Issue links
        for link in fields.get("issuelinks", []):
            type_name = (link.get("type") or {}).get("name", "")
            if not re.search(r"block|depend", type_name, re.IGNORECASE):
                continue
            if link.get("inwardIssue"):
                i = link["inwardIssue"]
                s = (i.get("fields") or {}).get("status") or {}
                lines.append(f"blocks|inward|{i['key']}|{s.get('name', '')}|{s.get('id', '')}")
            if link.get("outwardIssue"):
                o = link["outwardIssue"]
                s = (o.get("fields") or {}).get("status") or {}
                lines.append(f"blocks|outward|{o['key']}|{s.get('name', '')}|{s.get('id', '')}")

        # Parent
        parent = fields.get("parent")
        if parent:
            s = (parent.get("fields") or {}).get("status") or {}
            lines.append(f"parent|inward|{parent['key']}|{s.get('name', '')}|{s.get('id', '')}")

        # Subtasks
        for sub in fields.get("subtasks", []):
            s = (sub.get("fields") or {}).get("status") or {}
            lines.append(f"subtask|outward|{sub['key']}|{s.get('name', '')}|{s.get('id', '')}")

        # Labels
        for label in fields.get("labels", []):
            if re.match(r"^depends-on:", label, re.IGNORECASE):
                dep_key = label.split(":")[1].strip()
                lines.append(f"label|inward|{dep_key}|Unknown|")
            elif re.match(r"^blocked$", label, re.IGNORECASE):
                lines.append("label|inward||Unknown|")

        return "\n".join(lines)

    def discover(self) -> str:
        parts = ["=== Statuses ==="]
        try:
            data = self._request("GET", f"project/{self.config.board_project_key}/statuses")
            seen = set()
            for issue_type in data:
                for s in issue_type.get("statuses", []):
                    if s["id"] not in seen:
                        seen.add(s["id"])
                        parts.append(f"{s['id']} - {s['name']}")
        except Exception as e:
            parts.append(f"Error fetching statuses: {e}")

        parts.append("")
        parts.append("=== Transitions (from first issue) ===")
        try:
            search = self._request("POST", "search/jql", json={
                "jql": f"project={self.config.board_project_key} ORDER BY rank ASC",
                "maxResults": 1,
            })
            issues = search.get("issues", [])
            if issues:
                first_key = issues[0]["key"]
                trans_data = self._request("GET", f"issue/{first_key}/transitions")
                for t in trans_data.get("transitions", []):
                    parts.append(f"{t['id']} - {t['name']} -> {t['to']['name']} (id: {t['to']['id']})")
            else:
                parts.append("No issues found. Create an issue first, then run discover again.")
        except Exception as e:
            parts.append(f"Error fetching transitions: {e}")

        return "\n".join(parts)
