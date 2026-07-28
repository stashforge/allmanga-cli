"""Validation for externally supplied HTTP media URLs."""

import urllib.parse


def validate_http_url(url):
    if not isinstance(url, str) or any(ord(char) < 32 for char in url):
        raise ValueError("Invalid URL")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only HTTP(S) URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs with embedded credentials are not allowed")
    return url


def validate_stream_url(url):
    """Accept only credential-free HTTP(S) media and extractor destinations, or absolute local file paths."""
    import os
    if isinstance(url, str) and os.path.isabs(url):
        return url
    return validate_http_url(url)


def validate_optional_referer(referer):
    if not referer:
        return ""
    return validate_http_url(referer)


def is_supported_image(data):
    if data.startswith(b"\xff\xd8\xff"):
        return True
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data.startswith((b"GIF87a", b"GIF89a")):
        return True
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True
    return (
        len(data) >= 12
        and data[4:8] == b"ftyp"
        and data[8:12] in (b"avif", b"avis")
    )
