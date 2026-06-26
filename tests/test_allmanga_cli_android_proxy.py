import types
import unittest
from email.message import Message
from tests.app_namespace import load_app_namespace


class FakeServer:
    def __init__(self):
        self.shutdown_calls = 0
        self.close_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1

    def server_close(self):
        self.close_calls += 1


class AndroidProxyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_app_namespace(reload=True)
        self.globals = self.ns["play_android"].__globals__
        self.proxy_globals = self.ns[
            "replace_active_local_proxy"
        ].__globals__
        self.proxy_globals["_active_server"] = None
        self.original_subprocess_run = self.globals["subprocess"].run

    def tearDown(self):
        self.globals["subprocess"].run = self.original_subprocess_run
        self.ns["cleanup_active_local_proxy"]()

    def test_replacing_proxy_closes_previous_server(self):
        first = FakeServer()
        second = FakeServer()

        self.ns["replace_active_local_proxy"](first)
        self.ns["replace_active_local_proxy"](second)

        self.assertEqual(first.shutdown_calls, 1)
        self.assertEqual(first.close_calls, 1)
        self.assertIs(self.proxy_globals["_active_server"], second)

    def test_cleanup_closes_active_proxy_once(self):
        server = FakeServer()
        self.ns["replace_active_local_proxy"](server)

        self.ns["cleanup_active_local_proxy"]()
        self.ns["cleanup_active_local_proxy"]()

        self.assertEqual(server.shutdown_calls, 1)
        self.assertEqual(server.close_calls, 1)
        self.assertIsNone(self.proxy_globals["_active_server"])

    def test_successful_android_launch_keeps_proxy_for_player(self):
        server = FakeServer()
        self.globals["start_local_proxy"] = (
            lambda *args, **kwargs: ("http://127.0.0.1:1234/stream.mp4", server)
        )
        self.globals["subprocess"].run = lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0
        )
        stream = {
            "link": "https://example.test/video",
            "referer": "https://example.test/",
            "headers": {},
        }

        self.assertTrue(
            self.ns["play_android"](
                "Test", "1", stream, None, player="mpv"
            )
        )
        self.assertIs(self.proxy_globals["_active_server"], server)
        self.assertEqual(server.shutdown_calls, 0)

    def test_hls_with_headers_uses_hls_proxy_path(self):
        server = FakeServer()
        calls = []

        def start_proxy(*args, **kwargs):
            calls.append((args, kwargs))
            return "http://127.0.0.1:1234/stream.m3u8", server

        self.globals["start_local_proxy"] = start_proxy
        self.globals["subprocess"].run = lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0
        )
        stream = {
            "link": "https://example.test/video.m3u8",
            "type": "hls",
            "referer": "https://example.test/",
            "headers": {},
        }

        self.assertTrue(
            self.ns["play_android"](
                "Test", "1", stream, None, player="mpv"
            )
        )
        self.assertEqual(calls[0][1]["stream_type"], "hls")

    def test_dailymotion_av_stream_uses_local_m3u8_manifest(self):
        server = FakeServer()
        calls = []

        def start_content(content, filename, content_type):
            calls.append((content, filename, content_type))
            return "http://127.0.0.1:1234/stream.m3u8", server

        self.globals["start_local_content_server"] = start_content
        self.globals["subprocess"].run = lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0
        )
        stream = {
            "link": "https://vod.dmcdn.test/video/manifest.m3u8",
            "type": "hls",
            "referer": "",
            "headers": {},
            "dailymotion_video": "https://vod.dmcdn.test/video/manifest.m3u8",
            "dailymotion_audio": "https://vod.dmcdn.test/audio/manifest.m3u8",
            "dailymotion_width": 1280,
            "dailymotion_height": 720,
            "dailymotion_bandwidth": 2400,
        }

        self.assertTrue(
            self.ns["play_android"](
                "Test", "1", stream, None, player="mpv"
            )
        )
        self.assertEqual(calls[0][1], "stream.m3u8")
        self.assertEqual(calls[0][2], "application/vnd.apple.mpegurl")
        self.assertIn("EXT-X-MEDIA", calls[0][0])
        self.assertIn("https://vod.dmcdn.test/audio/manifest.m3u8", calls[0][0])

    def test_failed_android_launch_closes_new_proxy(self):
        server = FakeServer()
        self.globals["start_local_proxy"] = (
            lambda *args, **kwargs: ("http://127.0.0.1:1234/stream.mp4", server)
        )
        self.globals["subprocess"].run = lambda *args, **kwargs: types.SimpleNamespace(
            returncode=1
        )
        stream = {
            "link": "https://example.test/video",
            "referer": "https://example.test/",
            "headers": {},
        }

        self.assertFalse(
            self.ns["play_android"](
                "Test", "1", stream, None, player="mpv"
            )
        )
        self.assertEqual(server.shutdown_calls, 1)
        self.assertEqual(server.close_calls, 1)
        self.assertIsNone(self.proxy_globals["_active_server"])

    def test_direct_stream_launch_closes_previous_proxy(self):
        previous = FakeServer()
        self.ns["replace_active_local_proxy"](previous)
        self.globals["subprocess"].run = lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0
        )
        stream = {
            "link": "https://example.test/video",
            "referer": "",
            "headers": {},
        }

        self.assertTrue(
            self.ns["play_android"](
                "Test", "1", stream, None, player="mpv"
            )
        )
        self.assertEqual(previous.shutdown_calls, 1)
        self.assertIsNone(self.proxy_globals["_active_server"])


class AndroidProxySecurityTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_app_namespace(reload=True)

    def test_proxy_url_uses_random_secret_path(self):
        path = self.ns["_new_proxy_secret_path"]()
        self.assertRegex(path, r"^/[0-9a-f]{32}/stream\.mp4$")

    def test_proxy_url_can_use_hls_extension(self):
        path = self.ns["_new_proxy_secret_path"]("m3u8")
        self.assertRegex(path, r"^/[0-9a-f]{32}/stream\.m3u8$")

    def test_proxy_url_rejects_unsafe_extension(self):
        path = self.ns["_new_proxy_secret_path"]("../bad")
        self.assertRegex(path, r"^/[0-9a-f]{32}/stream\.mp4$")

    def test_wrong_path_never_reaches_upstream(self):
        secret = self.ns["_new_proxy_secret_path"]()
        self.assertTrue(
            self.ns["_proxy_path_authorized"](secret + "?x=1", secret)
        )
        self.assertFalse(
            self.ns["_proxy_path_authorized"](
                "/wrong/stream.mp4", secret
            )
        )

    def test_get_and_head_are_supported(self):
        self.assertTrue(self.ns["_proxy_method_allowed"]("GET"))
        self.assertTrue(self.ns["_proxy_method_allowed"]("HEAD"))
        self.assertEqual(
            self.ns["_proxy_range_header"]("bytes=0-3"), "bytes=0-3"
        )

    def test_other_methods_are_rejected(self):
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "PATCH"):
            self.assertFalse(self.ns["_proxy_method_allowed"](method))

    def test_unsafe_forwarded_headers_are_removed(self):
        filtered = self.ns["_proxy_filtered_headers"]({
            "X-Test": "forwarded",
            "Connection": "keep-alive",
            "Host": "attacker.invalid",
            "Content-Length": "999",
            "X-Bad": "line\nbreak",
        })

        self.assertEqual(filtered, {"X-Test": "forwarded"})

    def test_invalid_range_is_not_forwarded(self):
        self.assertEqual(
            self.ns["_proxy_range_header"]("bytes=0-3\r\nX-Bad: yes"),
            "",
        )
        self.assertEqual(self.ns["_proxy_range_header"]("items=0-3"), "")

    def test_hop_by_hop_response_headers_are_removed(self):
        headers = Message()
        headers["Connection"] = "X-Private"
        headers["X-Private"] = "secret"
        headers["Transfer-Encoding"] = "chunked"
        headers["Content-Type"] = "video/mp4"

        filtered = dict(self.ns["_proxy_response_headers"](headers))

        self.assertEqual(filtered, {"Content-Type": "video/mp4"})


if __name__ == "__main__":
    unittest.main()
