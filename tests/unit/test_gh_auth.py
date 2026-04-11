"""Unit tests for sortafit.gh_auth — GitHub App JWT generation and token refresh"""
import pytest
from unittest.mock import patch, MagicMock

from sortafit.config import Config
from sortafit.gh_auth import generate_github_app_token, refresh_gh_token


class TestRefreshGhToken:
    def test_noop_when_not_configured(self, tmp_path):
        config = Config(
            board_adapter="jira", board_domain="test.atlassian.net",
            board_project_key="TEST", target_repo=str(tmp_path),
            sorta_root=str(tmp_path),
            gh_app_id="", gh_app_installation_id="", gh_app_private_key_path="",
        )
        assert refresh_gh_token(config) is True

    def test_missing_key_file(self, tmp_path):
        config = Config(
            board_adapter="jira", board_domain="test.atlassian.net",
            board_project_key="TEST", target_repo=str(tmp_path),
            sorta_root=str(tmp_path),
            gh_app_id="12345", gh_app_installation_id="67890",
            gh_app_private_key_path=str(tmp_path / "nonexistent.pem"),
        )
        assert refresh_gh_token(config) is False


class TestGenerateToken:
    def test_missing_key_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            generate_github_app_token("123", "456", str(tmp_path / "missing.pem"))

    @patch("sortafit.gh_auth.requests.post")
    @patch("sortafit.gh_auth.time.time", return_value=1700000000)
    def test_jwt_exp_within_five_minutes(self, mock_time, mock_post, tmp_path):
        """JWT exp must be <=5 minutes from now to avoid clock-skew rejections."""
        import jwt as pyjwt

        key_file = tmp_path / "test.pem"
        # Generate a throwaway RSA key for the test
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_file.write_bytes(private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))

        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"token": "ghs_test123"},
        )

        generate_github_app_token("123", "456", str(key_file))

        # Decode the JWT that was sent to verify exp
        auth_header = mock_post.call_args[1]["headers"]["Authorization"]
        sent_jwt = auth_header.replace("Bearer ", "")
        public_key = private_key.public_key()
        claims = pyjwt.decode(sent_jwt, public_key, algorithms=["RS256"],
                              options={"verify_exp": False})

        # exp should be now + 300 (5 min), not now + 600 (10 min)
        assert claims["exp"] == 1700000000 + 300
        assert claims["iat"] == 1700000000 - 60
