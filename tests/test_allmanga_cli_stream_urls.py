import unittest

from allmanga_cli.media import resolver as stream_resolver
from tests.app_namespace import load_app_namespace
namespace = load_app_namespace()


class StreamUrlTests(unittest.TestCase):
    def test_stream_urls_require_credential_free_http(self):
        validate = namespace["validate_stream_url"]

        self.assertEqual(
            validate("https://cdn.example/video.mp4"),
            "https://cdn.example/video.mp4",
        )
        for url in (
            "file:///etc/passwd",
            "ftp://cdn.example/video.mp4",
            "https://user:secret@cdn.example/video.mp4",
            "https://cdn.example/video.mp4\nHeader: value",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate(url)

    def test_invalid_probe_url_never_reaches_urlopen(self):
        is_alive = namespace["is_alive"]
        original = is_alive.__globals__["urllib"].request.urlopen
        try:
            is_alive.__globals__["urllib"].request.urlopen = (
                lambda *args, **kwargs: self.fail("urlopen must not be called")
            )
            self.assertFalse(is_alive("file:///etc/passwd"))
        finally:
            is_alive.__globals__["urllib"].request.urlopen = original

    def test_invalid_embed_never_reaches_ytdlp(self):
        resolve_source = stream_resolver.resolve_source
        original_which = resolve_source.__globals__["shutil"].which
        original_popen = resolve_source.__globals__["subprocess"].Popen
        try:
            resolve_source.__globals__["shutil"].which = lambda name: "/usr/bin/yt-dlp"
            resolve_source.__globals__["subprocess"].Popen = (
                lambda *args, **kwargs: self.fail("yt-dlp must not be called")
            )
            streams = resolve_source(
                {"sourceName": "embed", "sourceUrl": "file:///etc/passwd"},
                silent=True,
            )
        finally:
            resolve_source.__globals__["shutil"].which = original_which
            resolve_source.__globals__["subprocess"].Popen = original_popen

        self.assertEqual(streams, [])

    def test_unsafe_extractor_output_is_discarded(self):
        resolve_source = stream_resolver.resolve_source
        globals_dict = resolve_source.__globals__
        original_which = globals_dict["shutil"].which
        original_popen = globals_dict["subprocess"].Popen
        original_read = globals_dict["read_bounded_process_stdout"]

        class Process:
            returncode = 0

        try:
            globals_dict["shutil"].which = lambda name: "/usr/bin/yt-dlp"
            globals_dict["subprocess"].Popen = lambda *args, **kwargs: Process()
            globals_dict["read_bounded_process_stdout"] = (
                lambda *args, **kwargs: b'{"url":"file:///etc/passwd"}'
            )
            streams = resolve_source(
                {
                    "sourceName": "embed",
                    "sourceUrl": "https://embed.example/watch",
                },
                silent=True,
            )
        finally:
            globals_dict["shutil"].which = original_which
            globals_dict["subprocess"].Popen = original_popen
            globals_dict["read_bounded_process_stdout"] = original_read

        self.assertEqual(streams, [])

    def test_mp4upload_uses_direct_page_extractor(self):
        resolve_source = stream_resolver.resolve_source
        globals_dict = resolve_source.__globals__
        original_urlopen = globals_dict["urllib"].request.urlopen
        original_is_alive = globals_dict["is_alive"]
        original_get_size = globals_dict["get_size"]

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, limit):
                return (
                    b'player.setup({src: "https:\\/\\/cdn.example\\/video.mp4"})'
                )

        try:
            globals_dict["urllib"].request.urlopen = (
                lambda *args, **kwargs: Response()
            )
            globals_dict["is_alive"] = lambda *args, **kwargs: True
            globals_dict["get_size"] = lambda *args, **kwargs: 1024
            streams = resolve_source({
                "sourceName": "Mp4",
                "sourceUrl": "https://mp4upload.com/embed-test.html",
            }, silent=True)
        finally:
            globals_dict["urllib"].request.urlopen = original_urlopen
            globals_dict["is_alive"] = original_is_alive
            globals_dict["get_size"] = original_get_size

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["link"], "https://cdn.example/video.mp4")
        self.assertEqual(
            streams[0]["referer"],
            "https://www.mp4upload.com/",
        )

    def test_pre_resolved_provider_stream_is_passed_through(self):
        streams = stream_resolver.resolve_source(
            {
                "sourceName": "Provider CDN",
                "streamUrl": "https://cdn.example/video.m3u8",
                "type": "hls",
                "resolution": "720p",
                "referer": "https://provider.example/watch",
                "headers": {"User-Agent": "Test", "Cookie": "secret=1"},
            },
            silent=True,
        )

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["source_name"], "Provider CDN")
        self.assertEqual(streams[0]["link"], "https://cdn.example/video.m3u8")
        self.assertEqual(streams[0]["type"], "hls")
        self.assertEqual(streams[0]["resolution"], "720p")
        self.assertEqual(streams[0]["referer"], "https://provider.example/watch")
        self.assertNotIn("Cookie", streams[0]["headers"])
        self.assertTrue(streams[0]["android_safe"])

    def test_pre_resolved_hls_without_headers_is_not_android_safe_by_default(self):
        streams = stream_resolver.resolve_source(
            {
                "sourceName": "Provider CDN",
                "streamUrl": "https://cdn.example/video.m3u8",
                "type": "hls",
            },
            silent=True,
        )

        self.assertEqual(len(streams), 1)
        self.assertFalse(streams[0]["android_safe"])

    def test_pre_resolved_provider_stream_rejects_unsafe_url(self):
        streams = stream_resolver.resolve_source(
            {
                "sourceName": "Provider CDN",
                "link": "file:///etc/passwd",
            },
            silent=True,
        )

        self.assertEqual(streams, [])


if __name__ == "__main__":
    unittest.main()
