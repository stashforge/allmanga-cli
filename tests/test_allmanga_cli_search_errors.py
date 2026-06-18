import io
import socket
import time
import unittest
import urllib.error
from tests.app_namespace import load_app_namespace
namespace = load_app_namespace()


class SearchErrorTests(unittest.TestCase):
    def test_failure_messages_are_specific_and_sanitized(self):
        message = namespace["search_failure_message"]
        response = io.BytesIO()
        http_error = urllib.error.HTTPError(
            "", 429, "", {}, response
        )

        try:
            self.assertEqual(
                message("AniList", http_error),
                "AniList rate limit reached. Try again later.",
            )
        finally:
            http_error.close()
        self.assertEqual(
            message("AllAnime", urllib.error.URLError(socket.timeout())),
            "AllAnime request timed out.",
        )
        self.assertEqual(
            message("AniList", urllib.error.URLError("offline")),
            "Could not connect to AniList.",
        )

    def test_allanime_checked_search_raises_typed_failure(self):
        search = namespace["search_anime"]
        globals_dict = search.__globals__
        original_req = globals_dict["_req"]
        try:
            globals_dict["_req"] = (
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    urllib.error.URLError(socket.timeout())
                )
            )
            with self.assertRaisesRegex(
                namespace["SearchFailure"], "timed out"
            ):
                search("slime", raise_errors=True)
        finally:
            globals_dict["_req"] = original_req

    def test_allanime_oneshot_separates_failure_from_empty_results(self):
        make_search = namespace["make_allanime_oneshot_search"]
        globals_dict = make_search.__globals__
        original_search = globals_dict["search_anime"]
        original_config = globals_dict["load_config"]
        try:
            globals_dict["load_config"] = lambda: {"anilist_token": ""}

            def failed(*args, **kwargs):
                raise namespace["SearchFailure"]("AllAnime request timed out.")

            globals_dict["search_anime"] = failed
            failed_search = make_search("slime", "sub")
            self._wait_until_done(failed_search[0])
            self.assertEqual(failed_search[1](), [])
            self.assertEqual(
                failed_search[3](), "AllAnime request timed out."
            )

            globals_dict["search_anime"] = lambda *args, **kwargs: []
            empty_search = make_search("nothing", "sub")
            self._wait_until_done(empty_search[0])
            self.assertEqual(empty_search[1](), [])
            self.assertEqual(empty_search[3](), "")
        finally:
            globals_dict["search_anime"] = original_search
            globals_dict["load_config"] = original_config

    def test_anilist_oneshot_exposes_typed_failure(self):
        make_search = namespace["make_anilist_oneshot_search"]
        globals_dict = make_search.__globals__
        original_search = globals_dict["search_anilist"]
        try:
            globals_dict["search_anilist"] = (
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    namespace["SearchFailure"](
                        "AniList authentication or access was rejected."
                    )
                )
            )
            search = make_search("token", "slime")
            self._wait_until_done(search[0])
        finally:
            globals_dict["search_anilist"] = original_search

        self.assertEqual(
            search[3](),
            "AniList authentication or access was rejected.",
        )

    def _wait_until_done(self, live_fn):
        deadline = time.time() + 2
        while time.time() < deadline:
            _items, _header, done = live_fn("")
            if done:
                return
            time.sleep(0.01)
        self.fail("background search did not finish")


if __name__ == "__main__":
    unittest.main()
