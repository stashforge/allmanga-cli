import unittest
from unittest.mock import patch

from tests.app_namespace import load_app_namespace

namespace = load_app_namespace()
fetch_cover_bytes = namespace["fetch_cover_bytes"]
validate_http_url = namespace["validate_http_url"]


class FakeResponse:
    def __init__(self, data, *, content_length=None, final_url="https://img.test/cover"):
        self.data = data
        self.offset = 0
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.final_url = final_url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.final_url

    def read(self, size=-1):
        if self.offset >= len(self.data):
            return b""
        end = len(self.data) if size < 0 else self.offset + size
        chunk = self.data[self.offset:end]
        self.offset += len(chunk)
        return chunk


class CoverSecurityTests(unittest.TestCase):
    def test_rejects_non_http_and_embedded_credentials(self):
        for url in ("file:///etc/passwd", "https://user:pass@example.test/cover"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_http_url(url)

    def test_secure_fetch_accepts_supported_image(self):
        image = b"\x89PNG\r\n\x1a\n" + b"image"
        response = FakeResponse(image, content_length=len(image))

        with patch.object(
            fetch_cover_bytes.__globals__["urllib"].request,
            "urlopen",
            return_value=response,
        ) as urlopen:
            result = fetch_cover_bytes("https://img.test/cover")

        self.assertEqual(result, image)
        self.assertIs(
            urlopen.call_args.kwargs["context"],
            fetch_cover_bytes.__globals__["SSL_CTX_SECURE"],
        )
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 5)

    def test_rejects_oversized_content_length(self):
        response = FakeResponse(b"", content_length=9)
        with patch.object(
            fetch_cover_bytes.__globals__["urllib"].request,
            "urlopen",
            return_value=response,
        ):
            with self.assertRaisesRegex(ValueError, "too large"):
                fetch_cover_bytes("https://img.test/cover", max_bytes=8)

    def test_rejects_stream_that_exceeds_limit(self):
        response = FakeResponse(b"\xff\xd8\xff" + b"x" * 10)
        with patch.object(
            fetch_cover_bytes.__globals__["urllib"].request,
            "urlopen",
            return_value=response,
        ):
            with self.assertRaisesRegex(ValueError, "too large"):
                fetch_cover_bytes("https://img.test/cover", max_bytes=8)

    def test_rejects_non_image_content(self):
        response = FakeResponse(b"<html>not an image</html>")
        with patch.object(
            fetch_cover_bytes.__globals__["urllib"].request,
            "urlopen",
            return_value=response,
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                fetch_cover_bytes("https://img.test/cover")


if __name__ == "__main__":
    unittest.main()
