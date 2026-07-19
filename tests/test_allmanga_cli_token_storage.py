import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.app_namespace import load_app_namespace
from allmanga_cli.state import paths as state_paths


class TokenStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.ns = load_app_namespace(reload=True)
        self.globals = self.ns["save_anilist_token"].__globals__
        self.config_path = Path(self.temp_dir.name) / "config.json"
        patcher = patch.object(state_paths, "CONFIG_PATH", str(self.config_path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_load_config_prefers_secret_backend_token(self):
        original_get = self.globals["secret_state"].get_secret
        try:
            self.globals["secret_state"].get_secret = lambda key: "secret-token"

            cfg = self.ns["load_config"]()

            self.assertEqual(cfg["anilist_token"], "secret-token")
        finally:
            self.globals["secret_state"].get_secret = original_get

    def test_save_token_uses_secret_backend_when_available(self):
        secret_state = self.globals["secret_state"]
        original_set = secret_state.set_secret
        stored = {}
        try:
            secret_state.set_secret = lambda key, value: stored.setdefault(key, value) or True
            cfg = {"anilist_token": "old"}

            mode = self.ns["save_anilist_token"](cfg, '"new-token"')

            self.assertEqual(mode, "secret")
            self.assertEqual(stored[secret_state.ANILIST_KEY], "new-token")
            self.assertEqual(cfg["anilist_token"], "new-token")
            self.assertNotIn("new-token", self.config_path.read_text())
        finally:
            secret_state.set_secret = original_set

    def test_save_token_falls_back_to_private_config(self):
        secret_state = self.globals["secret_state"]
        original_set = secret_state.set_secret
        try:
            secret_state.set_secret = lambda key, value: False
            cfg = {}

            mode = self.ns["save_anilist_token"](cfg, "plain-token")

            self.assertEqual(mode, "config")
            self.assertEqual(cfg["anilist_token"], "plain-token")
            self.assertIn("plain-token", self.config_path.read_text())
        finally:
            secret_state.set_secret = original_set

    def test_token_storage_status_does_not_expose_token(self):
        secret_state = self.globals["secret_state"]
        original_get = secret_state.get_secret
        original_backend = secret_state.backend_path
        try:
            secret_state.get_secret = lambda key: "secret-token"
            self.assertEqual(
                self.ns["anilist_token_storage_status"]({}),
                "secret",
            )

            secret_state.get_secret = lambda key: ""
            self.assertEqual(
                self.ns["anilist_token_storage_status"]({"anilist_token": "plain-token"}),
                "config",
            )
            self.assertEqual(
                self.ns["anilist_token_storage_status"]({"anilist_token": ""}),
                "none",
            )
            secret_state.backend_path = lambda: "/usr/bin/secret-tool"
            lines = self.ns["anilist_auth_status_lines"](
                {"anilist_token": "plain-token"}
            )
            rendered = "\n".join(lines)
            self.assertIn("AniList", rendered)
            self.assertIn("Token stored", rendered)
            self.assertIn("private config file", rendered)
            self.assertIn("/usr/bin/secret-tool", rendered)
            self.assertIn("plai", rendered)
            self.assertIn("oken", rendered)
            self.assertNotIn("plain-token", rendered)
            self.assertIn("move the token to keyring", rendered)

            lines = self.ns["anilist_auth_status_lines"](
                {"anilist_token": '"quoted-token"'}
            )
            rendered = "\n".join(lines)
            self.assertIn("wrapping quotes", rendered)
            self.assertNotIn('"quoted-token"', rendered)
        finally:
            secret_state.get_secret = original_get
            secret_state.backend_path = original_backend

    def test_short_token_mask_does_not_expose_value(self):
        self.assertEqual(self.ns["mask_token"]("abcd"), "****")
        self.assertEqual(
            self.ns["mask_token"]("abcdefghijklmnopqrstuvwxyz"),
            "abcd************wxyz",
        )
        self.assertEqual(self.ns["mask_token"](""), "")

    def test_existing_token_status_detects_login_guard(self):
        self.assertNotEqual(
            self.ns["anilist_token_storage_status"]({"anilist_token": "token"}),
            "none",
        )
        rendered = "\n".join(
            self.ns["anilist_auth_login_existing_lines"]({"anilist_token": "token"})
        )
        self.assertIn("Already authenticated", rendered)
        self.assertIn("auth logout", rendered)
        self.assertNotIn("Token:", rendered)
        self.assertNotIn("Config:", rendered)

    def test_token_command_output_is_masked_or_raw(self):
        cfg = {"anilist_token": "abcdefghijklmnopqrstuvwxyz"}
        secret_state = self.globals["secret_state"]
        original_get = secret_state.get_secret
        try:
            secret_state.get_secret = lambda key: None
            masked = self.ns["anilist_auth_token_lines"](cfg)
            raw = self.ns["anilist_auth_token_lines"](cfg, raw=True)

            self.assertEqual(masked[0], "AniList token: abcd************wxyz")
            self.assertIn("--raw", masked[1])
            self.assertEqual(raw, ["abcdefghijklmnopqrstuvwxyz"])
            self.assertIsNone(self.ns["anilist_auth_token_lines"]({}))
        finally:
            secret_state.get_secret = original_get

    def test_sensitive_text_redaction(self):
        jwt = "eyJ" + "a" * 30 + "." + "b" * 12 + "." + "c" * 12
        signed_url = (
            "https://cdn.example.test/video/stream.m3u8?"
            "Expires=999999&Signature=very-secret&Key-Pair-Id=abc"
        )
        text = f"Authorization: Bearer secret-token\nvalue={jwt}\nurl={signed_url}"

        redacted = self.ns["redact_sensitive_text"](text)

        self.assertIn("Authorization: Bearer <redacted>", redacted)
        self.assertIn("<redacted-jwt>", redacted)
        self.assertIn("https://cdn.example.test/video/stream.m3u8?<redacted>", redacted)
        self.assertNotIn("secret-token", redacted)
        self.assertNotIn(jwt, redacted)
        self.assertNotIn("Signature=very-secret", redacted)
        self.assertNotIn("Key-Pair-Id=abc", redacted)


if __name__ == "__main__":
    unittest.main()
