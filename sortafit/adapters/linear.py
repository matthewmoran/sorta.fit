"""Sorta.Fit Linear adapter — port of adapters/linear.sh"""
import json
import re

import requests

from sortafit.adapters.base import BoardAdapter
from sortafit.config import Config
from sortafit.utils import log_error


class LinearAdapter(BoardAdapter):
    """Linear GraphQL API adapter."""

    def __init__(self, config: Config):
        self.config = config
        domain = config.board_domain or "api.linear.app"
        self.api_url = f"https://{domain}/graphql"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.board_api_token}",
            "Content-Type": "application/json",
        })

    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query. Port of linear_graphql()."""
        payload = {"query": query, "variables": variables or {}}
        try:
            resp = self.session.post(self.api_url, json=payload)
        except requests.RequestException as e:
            log_error(f"Linear API request failed (network error): {e}")
            raise

        body = resp.text
        if resp.status_code >= 400 or (body and body[0] == "<"):
            log_error(f"Linear API error (HTTP {resp.status_code})")
            if body and body[0] == "<":
                log_error("Received HTML instead of JSON — check BOARD_API_TOKEN in .env")
            else:
                log_error(f"Response: {body[:200]}")
            raise requests.HTTPError(f"Linear API error (HTTP {resp.status_code})", response=resp)

        data = resp.json()
        errors = data.get("errors", [])
        if errors:
            log_error(f"Linear GraphQL error: {errors[0].get('message', 'Unknown error')}")
            raise RuntimeError(f"GraphQL error: {errors[0].get('message')}")

        return data

    def _query_issue(self, issue_key: str, fields: str) -> dict | None:
        """Query a Linear issue by identifier with given fields."""
        num = int(issue_key.rsplit("-", 1)[-1])
        data = self._graphql(
            f"query($teamKey: String!, $num: Float!) {{ issues(filter: {{ team: {{ key: {{ eq: $teamKey }} }}, number: {{ eq: $num }} }}, first: 1) {{ nodes {{ {fields} }} }} }}",
            {"teamKey": self.config.board_project_key, "num": float(num)},
        )
        nodes = data.get("data", {}).get("issues", {}).get("nodes", [])
        return nodes[0] if nodes else None

    def _resolve_id(self, issue_key: str) -> str:
        """Resolve an issue identifier to its internal UUID."""
        node = self._query_issue(issue_key, "id")
        return node["id"] if node else ""

    def get_cards_in_status(self, status: str, max_count: int = 10, start_at: int = 0) -> list[str]:
        if not status:
            log_error("No status ID configured for this runner. Check RUNNER_*_FROM in .env.")
            return []
        fetch_count = start_at + max_count
        data = self._graphql(
            "query($teamKey: String!, $stateId: String!, $count: Int!) { issues(filter: { team: { key: { eq: $teamKey } }, state: { id: { eq: $stateId } } }, first: $count, orderBy: createdAt) { nodes { id } } }",
            {"teamKey": self.config.board_project_key, "stateId": status, "count": fetch_count},
        )
        nodes = data.get("data", {}).get("issues", {}).get("nodes", [])
        return [n["id"] for n in nodes[start_at:]]

    def get_card_key(self, issue_id: str) -> str:
        data = self._graphql(
            "query($id: String!) { issue(id: $id) { identifier } }",
            {"id": issue_id},
        )
        return data["data"]["issue"]["identifier"]

    def get_card_title(self, issue_key: str) -> str:
        node = self._query_issue(issue_key, "title")
        return node["title"] if node else ""

    def get_card_type(self, issue_key: str) -> str:
        node = self._query_issue(issue_key, "labels { nodes { name } }")
        if node:
            labels = (node.get("labels") or {}).get("nodes", [])
            return labels[0]["name"] if labels else "Issue"
        return "Issue"

    def get_card_description(self, issue_key: str) -> str:
        node = self._query_issue(issue_key, "description")
        return (node.get("description") or "") if node else ""

    def get_card_comments(self, issue_key: str) -> str:
        node = self._query_issue(issue_key, "comments { nodes { body user { displayName } createdAt } }")
        if not node:
            return "No comments"
        comments = (node.get("comments") or {}).get("nodes", [])
        if not comments:
            return "No comments"
        parts = []
        for c in comments:
            parts.append("---")
            author = (c.get("user") or {}).get("displayName", "Unknown")
            parts.append(f"Author: {author}")
            parts.append(f"Date: {c.get('createdAt', '')}")
            parts.append(c.get("body", ""))
        return "\n".join(parts)

    def get_card_summary(self, issue_key: str) -> str:
        node = self._query_issue(issue_key, "identifier title state { name } priorityLabel labels { nodes { name } }")
        if not node:
            return "Issue not found"
        label_type = "Issue"
        labels = (node.get("labels") or {}).get("nodes", [])
        if labels:
            label_type = labels[0]["name"]
        return (
            f"Key: {node['identifier']}\n"
            f"Summary: {node['title']}\n"
            f"Status: {node['state']['name']}\n"
            f"Type: {label_type}\n"
            f"Priority: {node.get('priorityLabel') or 'None'}"
        )

    def update_description(self, issue_key: str, markdown: str) -> None:
        issue_id = self._resolve_id(issue_key)
        if not issue_id:
            log_error(f"Could not resolve Linear issue ID for {issue_key}")
            return
        self._graphql(
            "mutation($id: String!, $desc: String!) { issueUpdate(id: $id, input: { description: $desc }) { success } }",
            {"id": issue_id, "desc": markdown},
        )

    def add_comment(self, issue_key: str, comment: str) -> None:
        issue_id = self._resolve_id(issue_key)
        if not issue_id:
            log_error(f"Could not resolve Linear issue ID for {issue_key}")
            return
        self._graphql(
            "mutation($issueId: String!, $body: String!) { commentCreate(input: { issueId: $issueId, body: $body }) { success } }",
            {"issueId": issue_id, "body": comment},
        )

    def transition(self, issue_key: str, transition_id: str) -> None:
        issue_id = self._resolve_id(issue_key)
        if not issue_id:
            log_error(f"Could not resolve Linear issue ID for {issue_key}")
            return
        self._graphql(
            "mutation($id: String!, $stateId: String!) { issueUpdate(id: $id, input: { stateId: $stateId }) { success } }",
            {"id": issue_id, "stateId": transition_id},
        )

    def discover(self) -> str:
        parts = ["=== Statuses (Workflow States) ==="]
        try:
            data = self._graphql(
                "query($teamKey: String!) { teams(filter: { key: { eq: $teamKey } }) { nodes { states { nodes { id name type } } } } }",
                {"teamKey": self.config.board_project_key},
            )
            teams = data.get("data", {}).get("teams", {}).get("nodes", [])
            if not teams:
                parts.append("Team not found. Check BOARD_PROJECT_KEY.")
            else:
                for s in teams[0].get("states", {}).get("nodes", []):
                    safe = re.sub(r"[^a-zA-Z0-9_]", "_", s["id"])
                    parts.append(f"{s['id']} - {s['name']} ({s['type']})")
                    parts.append(f'  Config key: STATUS_{safe}="{s["name"]}"')
                    parts.append(f"  Transition: TRANSITION_TO_{safe}={s['id']}")
        except Exception as e:
            parts.append(f"Error: {e}")

        parts.extend(["", "=== Transitions ===",
            "Linear allows direct state-to-state transitions.",
            "Use the config keys above. The TRANSITION_TO value is the real UUID (with hyphens).",
            "RUNNER_*_FROM and RUNNER_*_TO in .env use the real UUID."])
        return "\n".join(parts)
