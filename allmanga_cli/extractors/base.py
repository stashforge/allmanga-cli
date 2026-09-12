"""Base class and common utilities for native video extractors."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
from typing import Any

from ..media.urls import validate_optional_referer, validate_stream_url
from ..services.http import SSL_CTX, UA

try:
    from curl_cffi import requests as cffi_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    cffi_requests = None
    CURL_CFFI_AVAILABLE = False


def _quality_from_height(height: int) -> tuple[str, int]:
    if height >= 1080:
        return "1080p", 1080
    if height >= 720:
        return "720p", 720
    if height >= 480:
        return "480p", 480
    if height >= 360:
        return "360p", 360
    return f"{height}p", height


class BaseExtractor:
    """Abstract base extractor matching Aniyomi's extractor pattern."""

    name: str = "Base"
    domains: list[str] = []
    patterns: list[re.Pattern] = []

    def can_handle(self, url: str) -> bool:
        """Return True if this extractor can handle the given URL."""
        if not url:
            return False
        parsed = urllib.parse.urlparse(url)
        host = (parsed.netloc or "").casefold()
        for domain in self.domains:
            if domain in host:
                return True
        for pattern in self.patterns:
            if pattern.search(url):
                return True
        return False

    def fetch_page(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        referer: str | None = None,
        cookies: dict[str, str] | None = None,
        timeout: int = 12,
    ) -> str:
        """Fetch page HTML/content using curl_cffi (with Chrome impersonation) or urllib."""
        req_headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if referer:
            req_headers["Referer"] = referer
        if headers:
            req_headers.update(headers)

        if CURL_CFFI_AVAILABLE and cffi_requests is not None:
            try:
                imp = "firefox147" if "Firefox" in req_headers.get("User-Agent", "") else "chrome"
                resp = cffi_requests.get(
                    url,
                    headers=req_headers,
                    cookies=cookies,
                    impersonate=imp,
                    timeout=timeout,
                    verify=False,
                )
                return resp.text
            except Exception:
                # Fall back to urllib if curl_cffi fails
                pass

        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="ignore")

    def extract_m3u8(
        self,
        master_url: str,
        *,
        referer: str = "",
        origin: str = "",
        name: str = "",
        priority: int = 2,
        headers: dict[str, str] | None = None,
        subtitles: list[dict] | None = None,
    ) -> list[dict]:
        """Parse master HLS playlist into quality streams or return master stream."""
        req_headers = headers.copy() if headers else {}
        if referer and "Referer" not in req_headers:
            req_headers["Referer"] = referer
        if origin and "Origin" not in req_headers:
            req_headers["Origin"] = origin
        if "User-Agent" not in req_headers:
            req_headers["User-Agent"] = UA

        try:
            content = self.fetch_page(master_url, headers=req_headers, referer=referer, timeout=8)
        except Exception:
            # If fetching manifest fails, return master stream directly
            content = ""

        prefix = name or self.name
        parsed_subs = list(subtitles or [])

        # Parse external subtitles in playlist
        if content:
            for sub_match in re.finditer(
                r'#EXT-X-MEDIA:TYPE=SUBTITLES.*?NAME="([^"]+)".*?URI="([^"]+)"',
                content,
                re.IGNORECASE,
            ):
                sub_label = sub_match.group(1)
                sub_uri = urllib.parse.urljoin(master_url, sub_match.group(2))
                parsed_subs.append({
                    "label": sub_label,
                    "url": sub_uri,
                    "default": "eng" in sub_label.casefold() or "en" in sub_label.casefold(),
                })

        # Check if master playlist has stream variants
        if content and "#EXT-X-STREAM-INF" in content:
            streams: list[dict] = []
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            i = 0
            while i < len(lines):
                line = lines[i]
                if line.startswith("#EXT-X-STREAM-INF"):
                    res_match = re.search(r"RESOLUTION=\d+x(\d+)", line)
                    bandwidth_match = re.search(r"BANDWIDTH=(\d+)", line)
                    height = int(res_match.group(1)) if res_match else 0
                    bitrate = int(bandwidth_match.group(1)) if bandwidth_match else 0
                    quality_str, rank = _quality_from_height(height) if height else ("Adaptive", 800)

                    # Next non-comment line is stream URL
                    stream_link = None
                    for j in range(i + 1, len(lines)):
                        if not lines[j].startswith("#"):
                            stream_link = lines[j]
                            i = j
                            break
                    if stream_link:
                        abs_link = urllib.parse.urljoin(master_url, stream_link)
                        stream_dict = {
                            "source_name": f"{prefix} ({quality_str})",
                            "link": abs_link,
                            "type": "hls",
                            "resolution": quality_str,
                            "referer": referer,
                            "headers": req_headers,
                            "source_priority": priority,
                            "android_safe": True,
                            "_quality_rank": rank,
                            "_bitrate": bitrate,
                        }
                        if parsed_subs:
                            stream_dict["subtitles"] = parsed_subs
                            def_sub = next((s["url"] for s in parsed_subs if s.get("default")), parsed_subs[0]["url"])
                            stream_dict["subtitle_url"] = def_sub
                        streams.append(stream_dict)
                i += 1

            if streams:
                streams.sort(key=lambda s: (s.get("_quality_rank", 0), s.get("_bitrate", 0)), reverse=True)
                return streams

        # Single stream fallback
        stream_dict = {
            "source_name": f"{prefix} (Adaptive)",
            "link": master_url,
            "type": "hls",
            "resolution": "Adaptive",
            "referer": referer,
            "headers": req_headers,
            "source_priority": priority,
            "android_safe": True,
            "_quality_rank": 800,
            "_bitrate": 0,
        }
        if parsed_subs:
            stream_dict["subtitles"] = parsed_subs
            def_sub = next((s["url"] for s in parsed_subs if s.get("default")), parsed_subs[0]["url"])
            stream_dict["subtitle_url"] = def_sub
        return [stream_dict]

    def extract(
        self,
        url: str,
        *,
        name: str = "",
        priority: int = 2,
        subtitles: list[dict] | None = None,
        headers: dict[str, str] | None = None,
        referer: str | None = None,
        **kwargs: Any,
    ) -> list[dict]:
        """Extract playable streams from embed URL. To be overridden by subclasses."""
        raise NotImplementedError
