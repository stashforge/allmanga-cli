"""Resolve provider source entries into playable streams."""

import json
import re
import shutil
import subprocess
import urllib.request

from ..core.processes import read_bounded_process_stdout
from ..core.terminal import sanitize_terminal_text
from ..services.allanime import get_clock_links
from ..services.http import (
    REFERER,
    SSL_CTX,
    UA,
    get_size,
    is_alive,
    request_json,
)
from .dash import resolve_dash_raw_urls
from .dailymotion import is_dailymotion_url, select_dailymotion_av_pair, stream_type_from_url
from .proxy_rules import proxy_filtered_headers
from .sources import decrypt_url, expand_wixmp, source_priority
from .urls import validate_optional_referer, validate_stream_url


_info = lambda message: None
_ok = lambda message: None
_warn = lambda message: None


def configure_reporters(info, ok, warn):
    global _info, _ok, _warn
    _info = info
    _ok = ok
    _warn = warn


def _pre_resolved_stream(source, name, priority, warn):
    stream_url = source.get("link") or source.get("streamUrl") or ""
    if not stream_url:
        return None
    try:
        stream_url = validate_stream_url(stream_url)
    except ValueError:
        warn(f"[{name}] rejected an unsafe stream URL")
        return []

    headers = {
        key: value
        for key, value in proxy_filtered_headers(source.get("headers") or {}).items()
        if key.casefold() not in {"authorization", "cookie"}
    }
    referer = source.get("referer") or headers.get("Referer", "")
    try:
        referer = validate_optional_referer(referer)
    except ValueError:
        referer = ""
        headers = {
            key: value
            for key, value in headers.items()
            if key.casefold() != "referer"
        }

    stream_type = str(source.get("type") or "").strip().lower()
    if stream_type not in {"mp4", "hls", "external", "dash"}:
        stream_type = "hls" if ".m3u8" in stream_url else "mp4"

    resolution = str(source.get("resolution") or "Adaptive")
    android_safe = source.get("android_safe")
    if android_safe is None:
        android_safe = stream_type == "mp4" or (
            stream_type == "hls" and bool(referer or headers)
        )

    return [{
        "source_name": name,
        "link": stream_url,
        "type": stream_type,
        "resolution": resolution,
        "referer": referer,
        "headers": headers,
        "source_priority": priority,
        "android_safe": bool(android_safe),
    }]


def _extract_mp4upload(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Referer": "https://youtu-chan.com/",
        },
    )
    with urllib.request.urlopen(
        request,
        context=SSL_CTX,
        timeout=12,
    ) as response:
        page = response.read(2 * 1024 * 1024).decode(
            "utf-8",
            errors="ignore",
        )
    match = re.search(
        r"""src\s*:\s*["']([^"']+)["']""",
        page,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return validate_stream_url(
        match.group(1).replace(r"\/", "/")
    )


def resolve_source(source, silent=False):
    name = sanitize_terminal_text(source.get("sourceName", "?")).title()
    name = re.sub(
        r"(?i)\b(mp4|hls|cdn|hd|tv)\b",
        lambda match: match.group(1).upper(),
        name,
    )
    name = re.sub(r"(?i)mp4upload", "Mp4Upload", name)
    url = source.get("sourceUrl", "")
    priority = source_priority(source)

    def info(message):
        if not silent:
            _info(message)

    def ok(message):
        if not silent:
            _ok(message)

    def warn(message):
        if not silent:
            _warn(message)

    result = []
    pre_resolved = _pre_resolved_stream(source, name, priority, warn)
    if pre_resolved is not None:
        return pre_resolved

    if not url:
        return result
    if not url.startswith("--"):
        try:
            url = validate_stream_url(url)
        except ValueError:
            warn(f"[{name}] rejected an unsafe stream URL")
            return result

    if "fast4speed" in url or "wixstatic" in url:
        info(f"[{name}] testing direct CDN ...")
        referer = "" if "wixstatic" in url else REFERER
        if is_alive(url, referer=referer):
            size = get_size(url, referer=referer)
            size_text = f"~{size // (1024 * 1024)} MB" if size else "?"
            ok(f"[{name}] direct mp4  size:{size_text}")
            result.append({
                "source_name": name,
                "link": url,
                "type": "mp4",
                "resolution": "1080p",
                "referer": referer,
                "headers": {},
                "source_priority": priority,
                "android_safe": True,
            })
        return result

    if url.startswith("--"):
        decrypted_path = decrypt_url(url[2:])
        info(f"[{name}] decrypting -> clock ...")
        items = get_clock_links(request_json, decrypted_path)
        if not items:
            warn(f"[{name}] clock returned no links")
            return result

        for item in items:
            dash_streams = resolve_dash_raw_urls(item, name, priority)
            if dash_streams:
                ok(
                    f"[{name}] DASH video + audio "
                    f"({dash_streams[0]['resolution']})"
                )
                result.extend(dash_streams)
                continue

            link = item.get("link", "")
            resolution = item.get("resolutionStr", "Adaptive")
            if not link:
                continue
            if "repackager.wixmp.com" in link:
                for label, mp4_url in expand_wixmp(link).items():
                    info(f"[{name}] testing wixmp {label} ...")
                    if is_alive(mp4_url, referer=""):
                        size = get_size(mp4_url, referer="")
                        size_text = (
                            f"~{size // (1024 * 1024)} MB"
                            if size
                            else "~340 MB"
                        )
                        ok(f"[{name}] wixmp-mp4 ({label})  size:{size_text}")
                        result.append({
                            "source_name": f"{name} wixmp ({label})",
                            "link": mp4_url,
                            "type": "mp4",
                            "resolution": label,
                            "referer": "",
                            "headers": {},
                            "source_priority": priority,
                            "android_safe": True,
                        })
                continue

            info(f"[{name}] testing {resolution} ...")
            working_referer = None
            for referer in (
                "",
                REFERER,
                "https://gogoanime.tel/",
                "https://anitaku.pe/",
                "https://yugenanime.tv/",
            ):
                if is_alive(link, referer=referer, timeout=6):
                    working_referer = referer
                    break
            if working_referer is not None:
                stream_type = "hls" if ".m3u8" in link else "mp4"
                ok(
                    f"[{name}] {stream_type} ({resolution})  "
                    f"ref:'{working_referer or 'none'}'"
                )
                result.append({
                    "source_name": f"{name} ({resolution})",
                    "link": link,
                    "type": stream_type,
                    "resolution": resolution,
                    "referer": working_referer,
                    "headers": {},
                    "source_priority": priority,
                    "android_safe": stream_type == "mp4",
                })
        return result

    if "mp4upload.com" in url.casefold():
        info(f"[{name}] extracting direct mp4 ...")
        try:
            stream_url = _extract_mp4upload(url)
        except Exception as exc:
            warn(f"[{name}] direct extraction failed: {exc}")
            stream_url = ""
        referer = "https://www.mp4upload.com/"
        if stream_url and is_alive(stream_url, referer=referer):
            size = get_size(stream_url, referer=referer)
            size_text = f"~{size // (1024 * 1024)} MB" if size else "?"
            ok(f"[{name}] direct mp4  size:{size_text}")
            result.append({
                "source_name": name,
                "link": stream_url,
                "type": "mp4",
                "resolution": "Adaptive",
                "referer": referer,
                "headers": {},
                "source_priority": priority,
                "android_safe": True,
            })
            return result

    if not shutil.which("yt-dlp"):
        warn(f"[{name}] yt-dlp not found, skipping embed")
        return result
    info(f"[{name}] extracting via yt-dlp ...")
    try:
        process = subprocess.Popen(
            ["yt-dlp", "-j", "--no-warnings", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        output = read_bounded_process_stdout(process, timeout=20)
        if process.returncode != 0:
            return result
        data = json.loads(output)
        formats = data.get("formats", [])
        streams = []
        if formats and is_dailymotion_url(url):
            video, audio = select_dailymotion_av_pair(formats)
            if video and audio:
                try:
                    video_url = validate_stream_url(video.get("url"))
                    audio_url = validate_stream_url(audio.get("url"))
                except ValueError:
                    video_url = audio_url = ""
                if video_url and audio_url:
                    height = video.get("height")
                    streams.append({
                        "source_name": f"{name} ({height}p)" if height else name,
                        "link": video_url,
                        "type": "hls",
                        "resolution": f"{height}p" if height else "Adaptive",
                        "referer": "",
                        "headers": {},
                        "source_priority": priority,
                        "android_safe": True,
                        "dailymotion_video": video_url,
                        "dailymotion_audio": audio_url,
                        "dailymotion_width": video.get("width") or 1280,
                        "dailymotion_height": video.get("height") or 720,
                        "dailymotion_bandwidth": video.get("tbr") or video.get("vbr") or 2400,
                    })
        if formats:
            for item in ([] if streams else formats):
                stream_url = item.get("url")
                if (
                    not stream_url
                    or item.get("acodec") == "none"
                    or item.get("vcodec") == "none"
                ):
                    continue
                try:
                    stream_url = validate_stream_url(stream_url)
                except ValueError:
                    continue
                height = item.get("height")
                headers = proxy_filtered_headers(
                    item.get("http_headers", data.get("http_headers", {}))
                )
                referer = headers.get("Referer", "")
                try:
                    referer = validate_optional_referer(referer)
                except ValueError:
                    referer = ""
                    headers = {
                        key: value
                        for key, value in headers.items()
                        if key.casefold() != "referer"
                    }
                streams.append({
                    "source_name": f"{name} ({height}p)" if height else name,
                    "link": stream_url,
                    "type": stream_type_from_url(stream_url),
                    "resolution": f"{height}p" if height else "Adaptive",
                    "referer": referer,
                    "headers": headers,
                    "source_priority": priority,
                    "android_safe": stream_type_from_url(stream_url) == "mp4",
                })
        else:
            stream_url = data.get("url")
            if stream_url:
                try:
                    stream_url = validate_stream_url(stream_url)
                except ValueError:
                    stream_url = ""
                if stream_url:
                    streams.append({
                        "source_name": name,
                        "link": stream_url,
                        "type": "external",
                        "resolution": "Adaptive",
                        "referer": "",
                        "headers": {},
                        "source_priority": priority,
                        "android_safe": False,
                    })
        if streams:
            ok(f"[{name}] yt-dlp found {len(streams)} stream(s)")
        result.extend(streams)
    except subprocess.TimeoutExpired:
        warn(f"[{name}] yt-dlp timed out")
    except Exception as exc:
        warn(f"[{name}] yt-dlp failed: {exc}")
    return result
