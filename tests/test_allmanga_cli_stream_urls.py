import runpy
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"
namespace = runpy.run_path(str(SCRIPT))


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
        resolve_source = namespace["resolve_source"]
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
        resolve_source = namespace["resolve_source"]
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


if __name__ == "__main__":
    unittest.main()
