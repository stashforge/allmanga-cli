import unittest

from allmanga_cli.media import resolver as stream_resolver
from allmanga_cli.media import ytdlp as ytdlp_extractor
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
        original_resolve = resolve_source.__globals__["resolve_ytdlp_embed"]
        try:
            resolve_source.__globals__["resolve_ytdlp_embed"] = (
                lambda *args, **kwargs: self.fail("yt-dlp extractor must not be called")
            )
            streams = resolve_source(
                {"sourceName": "embed", "sourceUrl": "file:///etc/passwd"},
                silent=True,
            )
        finally:
            resolve_source.__globals__["resolve_ytdlp_embed"] = original_resolve

        self.assertEqual(streams, [])

    def test_unsafe_extractor_output_is_discarded(self):
        resolve_source = stream_resolver.resolve_source
        globals_dict = ytdlp_extractor.__dict__
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

    def test_dailymotion_separate_audio_video_becomes_android_hls_manifest_stream(self):
        resolve_source = stream_resolver.resolve_source
        globals_dict = ytdlp_extractor.__dict__
        original_which = globals_dict["shutil"].which
        original_popen = globals_dict["subprocess"].Popen
        original_read = globals_dict["read_bounded_process_stdout"]

        class Process:
            returncode = 0

        payload = {
            "formats": [
                {
                    "url": "https://vod.dmcdn.test/video/manifest.m3u8",
                    "vcodec": "avc1",
                    "acodec": "none",
                    "height": 720,
                    "width": 1280,
                    "tbr": 2400,
                },
                {
                    "url": "https://vod.dmcdn.test/audio/manifest.m3u8",
                    "vcodec": "none",
                    "acodec": "aac",
                    "abr": 128,
                },
            ],
        }

        try:
            globals_dict["shutil"].which = lambda name: "/usr/bin/yt-dlp"
            globals_dict["subprocess"].Popen = lambda *args, **kwargs: Process()
            globals_dict["read_bounded_process_stdout"] = (
                lambda *args, **kwargs: __import__("json").dumps(payload).encode()
            )
            streams = resolve_source(
                {
                    "sourceName": "Dailymotion",
                    "sourceUrl": "https://www.dailymotion.com/video/xabc",
                },
                silent=True,
            )
        finally:
            globals_dict["shutil"].which = original_which
            globals_dict["subprocess"].Popen = original_popen
            globals_dict["read_bounded_process_stdout"] = original_read

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["type"], "hls")
        self.assertTrue(streams[0]["android_safe"])
        self.assertEqual(streams[0]["audio_url"], "https://vod.dmcdn.test/audio/manifest.m3u8")
        self.assertEqual(streams[0]["split_video_url"], "https://vod.dmcdn.test/video/manifest.m3u8")
        self.assertEqual(streams[0]["split_audio_url"], "https://vod.dmcdn.test/audio/manifest.m3u8")
        self.assertEqual(streams[0]["dailymotion_video"], "https://vod.dmcdn.test/video/manifest.m3u8")
        self.assertEqual(streams[0]["dailymotion_audio"], "https://vod.dmcdn.test/audio/manifest.m3u8")

    def test_generic_embed_uses_ytdlp_output_not_embed_page(self):
        resolve_source = stream_resolver.resolve_source
        globals_dict = ytdlp_extractor.__dict__
        original_which = globals_dict["shutil"].which
        original_popen = globals_dict["subprocess"].Popen
        original_read = globals_dict["read_bounded_process_stdout"]

        class Process:
            returncode = 0

        payload = {
            "formats": [{
                "url": "https://cdn.example.test/video.mp4",
                "vcodec": "avc1",
                "acodec": "aac",
                "height": 720,
            }]
        }

        try:
            globals_dict["shutil"].which = lambda name: "/usr/bin/yt-dlp"
            globals_dict["subprocess"].Popen = lambda *args, **kwargs: Process()
            globals_dict["read_bounded_process_stdout"] = (
                lambda *args, **kwargs: __import__("json").dumps(payload).encode()
            )
            streams = resolve_source(
                {
                    "sourceName": "Rumble",
                    "sourceUrl": "https://rumble.com/embed/vabc/",
                },
                silent=True,
            )
        finally:
            globals_dict["shutil"].which = original_which
            globals_dict["subprocess"].Popen = original_popen
            globals_dict["read_bounded_process_stdout"] = original_read

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["link"], "https://cdn.example.test/video.mp4")
        self.assertEqual(streams[0]["type"], "mp4")
        self.assertTrue(streams[0]["android_safe"])

    def test_generic_embed_streams_are_best_quality_first(self):
        streams = ytdlp_extractor.streams_from_ytdlp_data(
            {
                "formats": [
                    {
                        "url": "https://cdn.example.test/268.mp4",
                        "vcodec": "avc1",
                        "acodec": "aac",
                        "height": 268,
                    },
                    {
                        "url": "https://cdn.example.test/800.mp4",
                        "vcodec": "avc1",
                        "acodec": "aac",
                        "height": 800,
                    },
                    {
                        "url": "https://cdn.example.test/534.mp4",
                        "vcodec": "avc1",
                        "acodec": "aac",
                        "height": 534,
                    },
                ],
            },
            url="https://rumble.com/embed/vabc/",
            name="Rumble",
            priority=8,
        )

        self.assertEqual(
            [stream["resolution"] for stream in streams],
            ["800p"],
        )

    def test_rumble_best_format_url_is_kept_and_marked_hls(self):
        streams = ytdlp_extractor.streams_from_ytdlp_data(
            {
                "formats": [
                    {
                        "url": "https://cdn.example.test/low.tar?r_file=chunklist.m3u8",
                        "protocol": "m3u8_native",
                        "width": 640,
                        "height": 268,
                        "tbr": 222,
                    },
                    {
                        "url": (
                            "https://hugh.cdn.rumble.cloud/video/file.tar?"
                            "r_file=chunklist.m3u8&r_type=application%2Fvnd.apple.mpegurl"
                        ),
                        "protocol": "m3u8_native",
                        "width": 1280,
                        "height": 534,
                        "tbr": 2134,
                    },
                ],
            },
            url="https://rumble.com/embed/vabc/",
            name="Rumble",
            priority=8,
        )

        self.assertEqual(streams[0]["source_name"], "Rumble (1280x534)")
        self.assertEqual(streams[0]["type"], "hls")
        self.assertEqual(streams[0]["resolution"], "1280x534")
        self.assertEqual(
            streams[0]["link"],
            "https://hugh.cdn.rumble.cloud/video/file.tar?"
            "r_file=chunklist.m3u8&r_type=application%2Fvnd.apple.mpegurl",
        )
        self.assertNotIn("640x268", [stream["resolution"] for stream in streams])

    def test_video_only_format_gets_audio_url(self):
        streams = ytdlp_extractor.streams_from_ytdlp_data(
            {
                "formats": [
                    {
                        "url": "https://cdn.example.test/best-video.m3u8",
                        "protocol": "m3u8_native",
                        "width": 1920,
                        "height": 800,
                        "acodec": "none",
                        "vcodec": "avc1",
                    },
                    {
                        "url": "https://cdn.example.test/audio-low.aac",
                        "vcodec": "none",
                        "acodec": "aac",
                        "abr": 96,
                    },
                    {
                        "url": "https://cdn.example.test/audio-best.aac",
                        "vcodec": "none",
                        "acodec": "aac",
                        "abr": 192,
                    },
                ],
            },
            url="https://rumble.com/embed/vabc/",
            name="Rumble",
            priority=8,
        )

        self.assertEqual(streams[0]["link"], "https://cdn.example.test/best-video.m3u8")
        self.assertEqual(streams[0]["audio_url"], "https://cdn.example.test/audio-best.aac")
        self.assertEqual(streams[0]["split_video_url"], "https://cdn.example.test/best-video.m3u8")
        self.assertEqual(streams[0]["split_audio_url"], "https://cdn.example.test/audio-best.aac")
        self.assertTrue(streams[0]["android_safe"])

    def test_dailymotion_ytdlp_retries_before_giving_up(self):
        globals_dict = ytdlp_extractor.__dict__
        original_which = globals_dict["shutil"].which
        original_popen = globals_dict["subprocess"].Popen
        original_read = globals_dict["read_bounded_process_stdout"]
        calls = []

        class Process:
            returncode = 1

        try:
            globals_dict["shutil"].which = lambda name: "/usr/bin/yt-dlp"
            globals_dict["subprocess"].Popen = lambda *args, **kwargs: (
                calls.append(args) or Process()
            )
            globals_dict["read_bounded_process_stdout"] = lambda *args, **kwargs: b""
            streams = ytdlp_extractor.resolve_ytdlp_embed(
                "https://www.dailymotion.com/video/xabc",
                name="Dailymotion",
                priority=8,
                ok=lambda _message: None,
                warn=lambda _message: None,
            )
        finally:
            globals_dict["shutil"].which = original_which
            globals_dict["subprocess"].Popen = original_popen
            globals_dict["read_bounded_process_stdout"] = original_read

        self.assertEqual(streams, [])
        self.assertEqual(len(calls), 3)
        self.assertNotIn("-f", calls[0][0])

    def test_non_dailymotion_ytdlp_uses_plain_json_and_reads_format_url(self):
        globals_dict = ytdlp_extractor.__dict__
        original_which = globals_dict["shutil"].which
        original_popen = globals_dict["subprocess"].Popen
        original_read = globals_dict["read_bounded_process_stdout"]
        calls = []

        class Process:
            returncode = 0

        payload = {
            "formats": [{
                "url": "https://cdn.example.test/best.mp4",
                "height": 720,
                "vcodec": "avc1",
            }],
        }

        try:
            globals_dict["shutil"].which = lambda name: "/usr/bin/yt-dlp"
            globals_dict["subprocess"].Popen = lambda *args, **kwargs: (
                calls.append(args) or Process()
            )
            globals_dict["read_bounded_process_stdout"] = (
                lambda *args, **kwargs: __import__("json").dumps(payload).encode()
            )
            streams = ytdlp_extractor.resolve_ytdlp_embed(
                "https://rumble.com/embed/vabc/",
                name="Rumble",
                priority=8,
                ok=lambda _message: None,
                warn=lambda _message: None,
            )
        finally:
            globals_dict["shutil"].which = original_which
            globals_dict["subprocess"].Popen = original_popen
            globals_dict["read_bounded_process_stdout"] = original_read

        self.assertEqual(streams[0]["link"], "https://cdn.example.test/best.mp4")
        self.assertNotIn("-f", calls[0][0])

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
