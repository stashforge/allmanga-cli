import runpy
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"
API_UTILS = (
    Path(__file__).resolve().parents[1]
    / "allmanga_cli"
    / "api_utils.py"
)
namespace = runpy.run_path(str(SCRIPT))
anilist_urlopen = namespace["anilist_urlopen"]
account_cache_key = namespace["anilist_account_cache_key"]
read_limited_response = namespace["read_limited_response"]
read_json_response = namespace["read_json_response"]


class FakeResponse:
    def __init__(self, data, content_length=None):
        self.stream = BytesIO(data)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def read(self, size=-1):
        return self.stream.read(size)


class AniListHttpTests(unittest.TestCase):
    def test_shared_request_uses_secure_context_and_timeout(self):
        request = object()
        data = b"graphql"
        response = object()

        with patch.object(
            anilist_urlopen.__globals__["urllib"].request,
            "urlopen",
            return_value=response,
        ) as urlopen:
            result = anilist_urlopen(request, data)

        self.assertIs(result, response)
        urlopen.assert_called_once_with(
            request,
            data=data,
            context=anilist_urlopen.__globals__["SSL_CTX_SECURE"],
            timeout=anilist_urlopen.__globals__["ANILIST_TIMEOUT"],
        )

    def test_all_anilist_calls_use_shared_request_helper(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertEqual(source.count("with anilist_urlopen("), 6)
        self.assertNotIn("data=data, context=SSL_CTX_SECURE) as r", source)
        self.assertNotIn("data=data_mut, context=SSL_CTX_SECURE) as r", source)
        self.assertNotIn("data=data_list, context=SSL_CTX_SECURE) as r", source)

    def test_account_cache_key_is_stable_and_account_specific(self):
        first = account_cache_key("token-one")
        second = account_cache_key("token-two")

        self.assertEqual(first, account_cache_key("token-one"))
        self.assertNotEqual(first, second)
        self.assertNotIn("token-one", first)
        self.assertEqual(account_cache_key(""), "anonymous")

    def test_list_and_search_cache_keys_include_account_scope(self):
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertIn(
            "anilist_account_cache_key(token),\n"
            "        str(status or \"ALL\").upper(),",
            source,
        )
        self.assertIn(
            "anilist_account_cache_key(token),\n"
            "        str(query or \"\").strip().casefold(),",
            source,
        )
        self.assertNotIn(
            "cache_key = (bool(token), str(query or \"\").strip().lower())",
            source,
        )

    def test_declared_oversized_response_is_rejected_before_read(self):
        response = FakeResponse(b"{}", content_length=100)

        with self.assertRaisesRegex(ValueError, "too large"):
            read_limited_response(response, max_bytes=10)

        self.assertEqual(response.stream.tell(), 0)

    def test_undeclared_oversized_response_is_rejected(self):
        response = FakeResponse(b"x" * 11)

        with self.assertRaisesRegex(ValueError, "too large"):
            read_limited_response(response, max_bytes=10)

    def test_valid_bounded_json_response_is_decoded(self):
        response = FakeResponse(b'{"ok": true}', content_length=12)

        self.assertEqual(
            read_json_response(response, max_bytes=32),
            {"ok": True},
        )

    def test_api_json_reads_use_bounded_decoder(self):
        source = (
            SCRIPT.read_text(encoding="utf-8")
            + API_UTILS.read_text(encoding="utf-8")
        )

        self.assertNotRegex(source, r"json\.loads\([^\\n]*\.read\(")
        self.assertGreaterEqual(source.count("read_json_response("), 8)


if __name__ == "__main__":
    unittest.main()
