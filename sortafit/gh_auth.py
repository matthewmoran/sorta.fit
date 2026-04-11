"""Sorta.Fit GitHub App authentication — port of core/gh-auth.sh + core/gh-token.js"""
import os
import time
from pathlib import Path

import jwt
import requests

from sortafit.config import Config
from sortafit.utils import log_error, log_info


def generate_github_app_token(app_id: str, installation_id: str, private_key_path: str) -> str:
    """Generate a GitHub App installation access token.

    Port of core/gh-token.js — generates JWT with RS256, exchanges for installation token.
    """
    key_path = Path(private_key_path)
    if not key_path.exists():
        raise FileNotFoundError(f"Private key not found: {private_key_path}")

    private_key = key_path.read_bytes()

    now = int(time.time())
    payload = {
        "iat": now - 60,   # 60s clock skew allowance
        "exp": now + 300,  # 5 min expiry — leaves headroom under GitHub's 10 min max
        "iss": app_id,
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")

    resp = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "sorta-fit-bot",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if resp.status_code != 201:
        raise RuntimeError(f"GitHub API error (HTTP {resp.status_code}): {resp.text}")

    installation_token = resp.json().get("token")
    if not installation_token:
        raise RuntimeError(f"No token in response: {resp.text}")

    return installation_token


def refresh_gh_token(config: Config) -> bool:
    """Refresh the GitHub App installation token. Port of refresh_gh_token().

    Sets GH_TOKEN env var so gh CLI and git push use the bot identity.
    Returns True on success, False on failure. No-op if not configured.
    """
    if not config.gh_app_id or not config.gh_app_installation_id or not config.gh_app_private_key_path:
        return True  # Not configured — graceful no-op

    try:
        token = generate_github_app_token(
            config.gh_app_id,
            config.gh_app_installation_id,
            config.gh_app_private_key_path,
        )
        # Store on config for review runner — don't set GH_TOKEN globally,
        # otherwise the code runner creates PRs as the bot and the bot
        # can't review its own PRs.
        config.gh_app_token = token
        log_info("GitHub App token refreshed (sorta-fit-bot)")
        return True
    except Exception as e:
        log_error(f"Failed to generate GitHub App token: {e}")
        return False
