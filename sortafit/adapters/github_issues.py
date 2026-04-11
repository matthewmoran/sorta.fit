"""Sorta.Fit GitHub Issues adapter — port of adapters/github-issues.sh"""
import json
import re
import subprocess
from urllib.parse import quote

import requests

from sortafit.adapters.base import BoardAdapter
from sortafit.config import Config
from sortafit.utils import find_gh, log_error


class GitHubIssuesAdapter(BoardAdapter):
    """GitHub Issues REST API adapter with gh CLI fallback."""

    def __init__(self, config: Config):
        self.config = config
        self.repo = config.board_project_key  # owner/repo format
        self.gh_cmd = find_gh()
        domain = config.board_domain or "github.com"
        if domain == "github.com":
            self.api_base = "https://api.github.com"
        else:
            self.api_base = f"https://{domain}/api/v3"

        # Check if gh CLI is authenticated
        self.use_cli = False
        try:
            result = subprocess.run(
                [self.gh_cmd, "auth", "status"],
                capture_output=True, text=True, encoding="utf-8"
            )
            self.use_cli = result.returncode == 0
        except FileNotFoundError:
            pass

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if config.board_api_token:
            self.session.headers["Authorization"] = f"token {config.board_api_token}"

    def _api(self, method: str, endpoint: str, data: str = "") -> dict | list:
        """Make a GitHub API request. Port of github_api()."""
        # Try gh CLI first
        if self.use_cli:
            try:
                args = [self.gh_cmd, "api", endpoint, "--method", method]
                if data:
                    args.extend(["--input", "-"])
                result = subprocess.run(
                    args, input=data if data else None,
                    capture_output=True, text=True, encoding="utf-8"
                )
                if result.returncode == 0:
                    return json.loads(result.stdout) if result.stdout.strip() else {}
                else:
                    log_error(f"GitHub API error via gh CLI: {result.stderr[:200]}")
                    raise RuntimeError(f"gh CLI error: {result.stderr[:200]}")
            except FileNotFoundError:
                pass  # Fall through to requests

        # Fallback: requests with token
        url = f"{self.api_base}{endpoint}"
        try:
            resp = self.session.request(
                method, url,
                data=data if data else None,
                headers={"Content-Type": "application/json"} if data else {},
            )
        except requests.RequestException as e:
            log_error(f"GitHub API request failed (network error): {e}")
            raise

        body = resp.text
        if resp.status_code >= 400 or (body and body[0] == "<"):
            log_error(f"GitHub API error (HTTP {resp.status_code})")
            if body and body[0] == "<":
                log_error("Received HTML instead of JSON — check BOARD_API_TOKEN in .env")
            else:
                log_error(f"Response: {body[:200]}")
            raise requests.HTTPError(f"GitHub API error (HTTP {resp.status_code})", response=resp)

        return resp.json() if body.strip() else {}

    @staticmethod
    def _issue_number(key: str) -> str:
        """Strip GH- or # prefix to get raw issue number."""
        key = key.removeprefix("GH-")
        return key.lstrip("#")

    def get_cards_in_status(self, status: str, max_count: int = 10, start_at: int = 0) -> list[str]:
        if not status:
            log_error("No status ID configured for this runner. Check RUNNER_*_FROM in .env.")
            return []

        encoded = quote(status)
        fetch_count = start_at + max_count
        all_numbers: list[str] = []
        page = 1
        per_page = min(100, fetch_count)

        while True:
            data = self._api("GET",
                f"/repos/{self.repo}/issues?labels={encoded}&state=open&per_page={per_page}&page={page}&sort=created&direction=asc")
            if not isinstance(data, list):
                break
            # Filter out PRs
            issues = [i for i in data if "pull_request" not in i]
            all_numbers.extend(str(i["number"]) for i in issues)

            if len(all_numbers) >= fetch_count or len(data) < per_page:
                break
            page += 1

        return all_numbers[start_at:start_at + max_count]

    def get_card_key(self, issue_id: str) -> str:
        data = self._api("GET", f"/repos/{self.repo}/issues/{issue_id}")
        return f"GH-{data['number']}"

    def get_card_title(self, issue_key: str) -> str:
        num = self._issue_number(issue_key)
        data = self._api("GET", f"/repos/{self.repo}/issues/{num}")
        return data["title"]

    def get_card_type(self, issue_key: str) -> str:
        num = self._issue_number(issue_key)
        data = self._api("GET", f"/repos/{self.repo}/issues/{num}")
        labels = data.get("labels", [])
        type_labels = ["bug", "feature", "task", "enhancement"]
        for label in labels:
            name = label["name"] if isinstance(label, dict) else label
            if name.lower() in type_labels:
                return name
        return "Issue"

    def get_card_description(self, issue_key: str) -> str:
        num = self._issue_number(issue_key)
        data = self._api("GET", f"/repos/{self.repo}/issues/{num}")
        return data.get("body") or ""

    def get_card_comments(self, issue_key: str) -> str:
        num = self._issue_number(issue_key)
        data = self._api("GET", f"/repos/{self.repo}/issues/{num}/comments?per_page=100")
        if not isinstance(data, list) or not data:
            return "No comments"
        parts = []
        for c in data:
            parts.append("---")
            author = (c.get("user") or {}).get("login", "Unknown")
            parts.append(f"Author: {author}")
            parts.append(f"Date: {c.get('created_at', '')}")
            parts.append(c.get("body", ""))
        return "\n".join(parts)

    def get_card_summary(self, issue_key: str) -> str:
        num = self._issue_number(issue_key)
        data = self._api("GET", f"/repos/{self.repo}/issues/{num}")
        labels = data.get("labels", [])
        label_names = [l["name"] if isinstance(l, dict) else l for l in labels]
        status_label = next((n for n in label_names if n.startswith("status:")), None)
        status_name = status_label.replace("status:", "") if status_label else "open"
        type_labels = ["bug", "feature", "task", "enhancement"]
        card_type = next((n for n in label_names if n.lower() in type_labels), "Issue")
        priority = next((n.replace("priority:", "") for n in label_names if n.startswith("priority:")), "None")
        return (
            f"Key: GH-{data['number']}\n"
            f"Summary: {data['title']}\n"
            f"Status: {status_name}\n"
            f"Type: {card_type}\n"
            f"Priority: {priority}"
        )

    def update_description(self, issue_key: str, markdown: str) -> None:
        num = self._issue_number(issue_key)
        self._api("PATCH", f"/repos/{self.repo}/issues/{num}",
                  json.dumps({"body": markdown}))

    def add_comment(self, issue_key: str, comment: str) -> None:
        num = self._issue_number(issue_key)
        self._api("POST", f"/repos/{self.repo}/issues/{num}/comments",
                  json.dumps({"body": comment}))

    def transition(self, issue_key: str, transition_id: str) -> None:
        num = self._issue_number(issue_key)
        data = self._api("GET", f"/repos/{self.repo}/issues/{num}")
        labels = data.get("labels", [])
        label_names = [l["name"] if isinstance(l, dict) else l for l in labels]
        new_labels = [n for n in label_names if not n.startswith("status:")]
        new_labels.append(transition_id)
        self._api("PATCH", f"/repos/{self.repo}/issues/{num}",
                  json.dumps({"labels": new_labels}))

    def discover(self) -> str:
        parts = ["=== Statuses (Labels) ==="]
        try:
            data = self._api("GET", f"/repos/{self.repo}/labels?per_page=100")
            if not isinstance(data, list):
                parts.append("Could not fetch labels. Check BOARD_PROJECT_KEY (should be owner/repo).")
            else:
                status_labels = [l for l in data if isinstance(l, dict) and l.get("name", "").startswith("status:")]
                if not status_labels:
                    parts.append('No status: labels found.')
                    parts.append('Create labels with a "status:" prefix (e.g., status:todo, status:refined).')
                    parts.append("")
                    parts.append("All labels in this repo:")
                    for l in data:
                        parts.append(f"  {l['name']} - {l.get('description') or '(no description)'}")
                else:
                    for l in status_labels:
                        safe = re.sub(r"[^a-zA-Z0-9_]", "_", l["name"])
                        display = l.get("description") or l["name"].replace("status:", "")
                        parts.append(f"{l['name']} - {display}")
                        parts.append(f'  Config key: STATUS_{safe}="{display}"')
                        parts.append(f"  Transition: TRANSITION_TO_{safe}={l['name']}")
        except Exception as e:
            parts.append(f"Error: {e}")

        parts.extend(["", "=== Transitions ===",
            "GitHub Issues uses label swaps for transitions.",
            "Config keys use underscores (bash-safe). Config values use real label names.",
            'RUNNER_*_FROM and RUNNER_*_TO in .env use the real label names (e.g., status:todo).'])
        return "\n".join(parts)
