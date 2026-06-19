import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from allmanga_cli.services import anilist as anilist_service
from tests.app_namespace import load_app_namespace

APP = Path(__file__).resolve().parents[1] / "allmanga_cli" / "app.py"
API_UTILS = (
    Path(__file__).resolve().parents[1]
    / "allmanga_cli"
    / "core"
    / "api.py"
)
namespace = load_app_namespace()
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
    def test_list_entry_progress_survives_without_nested_media_list_entry(self):
        media = {
            "id": 123,
            "title": {"romaji": "Tracked Show"},
            "format": "TV",
            "episodes": 24,
            "status": "FINISHED",
        }
        entry = {
            "progress": 5,
            "updatedAt": 123456,
            "startedAt": {"year": 2026, "month": 6, "day": 1},
            "completedAt": {},
        }

        show = anilist_service.normalize_media(
            media,
            list_name="CURRENT",
            entry=entry,
        )

        self.assertEqual(show["_anilist_list"], "CURRENT")
        self.assertEqual(show["_anilist_progress"], 5)
        self.assertEqual(show["_anilist_updated_at"], 123456)

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
        app_source = APP.read_text(encoding="utf-8")
        service_source = (
            APP.parent / "services" / "anilist.py"
        ).read_text(encoding="utf-8")

        self.assertIn("anilist_service.fetch_media(", app_source)
        self.assertIn("anilist_service.fetch_list(", app_source)
        self.assertIn("anilist_service.search(", app_source)
        self.assertIn("with urlopen(_request(token)", service_source)
        self.assertNotIn("urllib.request.urlopen(", service_source)
        self.assertNotIn("context=SSL_CTX_SECURE", service_source)

    def test_account_cache_key_is_stable_and_account_specific(self):
        first = account_cache_key("token-one")
        second = account_cache_key("token-two")

        self.assertEqual(first, account_cache_key("token-one"))
        self.assertNotEqual(first, second)
        self.assertNotIn("token-one", first)
        self.assertEqual(account_cache_key(""), "anonymous")

    def test_list_and_search_cache_keys_include_account_scope(self):
        source = APP.read_text(encoding="utf-8")

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
        package_root = APP.parent
        source = "".join(
            path.read_text(encoding="utf-8")
            for path in package_root.rglob("*.py")
        )

        self.assertNotRegex(source, r"json\.loads\([^\\n]*\.read\(")
        self.assertIn(
            "anilist_service.fetch_media(\n"
            "            anilist_urlopen,\n"
            "            read_json_response,",
            source,
        )
        self.assertIn(
            "anilist_service.fetch_list(\n"
            "            anilist_urlopen,\n"
            "            read_json_response,",
            source,
        )
        self.assertIn(
            "anilist_service.search(\n"
            "            anilist_urlopen,\n"
            "            read_json_response,",
            source,

        )

    def test_update_entry_sends_start_and_completed_dates(self):
        observed = {}

        def urlopen(request, payload):
            observed.update(json_payload=payload.decode())
            return FakeContext({"data": {"SaveMediaListEntry": {"id": 1}}})

        anilist_service.update_entry(
            urlopen,
            lambda response: response.data,
            "token",
            123,
            progress=12,
            status="COMPLETED",
            started_at={"year": 2026, "month": 6, "day": 18},
            completed_at={"year": 2026, "month": 6, "day": 18},
        )

        self.assertIn("startedAt", observed["json_payload"])
        self.assertIn("completedAt", observed["json_payload"])
        self.assertIn('"startedAt": {"year": 2026, "month": 6, "day": 18}', observed["json_payload"])
        self.assertIn('"completedAt": {"year": 2026, "month": 6, "day": 18}', observed["json_payload"])


class FakeContext:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


if __name__ == "__main__":
    unittest.main()
