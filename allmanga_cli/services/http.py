"""Shared HTTP transport, TLS contexts, and media probes."""

import json
import re
import ssl
import urllib.request

from ..core.api import read_json_response
from ..media.urls import validate_optional_referer, validate_stream_url


SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE
SSL_CTX_SECURE = ssl.create_default_context()

ANILIST_TIMEOUT = 8
API_BASE = "https://api.allanime.day/api"
CLOCK_BASE = "allanime.day"
REFERER = "https://allmanga.to/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
BASE_HDRS = {
    "User-Agent": UA,
    "Origin": "https://allmanga.to",
    "Referer": REFERER,
    "sec-ch-ua-platform": '"Windows"',
}


def anilist_urlopen(request, data):
    return urllib.request.urlopen(
        request,
        data=data,
        context=SSL_CTX_SECURE,
        timeout=ANILIST_TIMEOUT,
    )


def request_json(url, data=None, extra_hdrs=None, timeout=8):
    headers = {**BASE_HDRS, **(extra_hdrs or {})}
    if data:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(
        request,
        context=SSL_CTX_SECURE,
        timeout=timeout,
    ) as response:
        return read_json_response(response)


def is_alive(url, referer="", timeout=6):
    try:
        url = validate_stream_url(url)
        referer = validate_optional_referer(referer)
    except ValueError:
        return False
    headers = {"User-Agent": UA, "Range": "bytes=0-0"}
    if referer:
        headers["Referer"] = referer
    for method in ("GET", "HEAD"):
        try:
            request = urllib.request.Request(
                url, headers=headers, method=method
            )
            with urllib.request.urlopen(
                request,
                context=SSL_CTX,
                timeout=timeout,
            ) as response:
                return 200 <= response.status < 400
        except Exception:
            continue
    return False


def get_size(url, referer="", timeout=6):
    try:
        url = validate_stream_url(url)
        referer = validate_optional_referer(referer)
    except ValueError:
        return None
    headers = {"User-Agent": UA, "Range": "bytes=0-0"}
    if referer:
        headers["Referer"] = referer
    try:
        request = urllib.request.Request(
            url, headers=headers, method="GET"
        )
        with urllib.request.urlopen(
            request,
            context=SSL_CTX,
            timeout=timeout,
        ) as response:
            if 200 <= response.status < 400:
                match = re.search(
                    r"/(\d+)",
                    response.headers.get("Content-Range", ""),
                )
                return int(match.group(1)) if match else None
    except Exception:
        pass
    return None
