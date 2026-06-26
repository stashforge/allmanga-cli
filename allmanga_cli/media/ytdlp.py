"""yt-dlp based embed extraction."""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse

from ..core.processes import read_bounded_process_stdout
from .dailymotion import is_dailymotion_url, stream_type_from_url
from .proxy_rules import proxy_filtered_headers
from .urls import validate_optional_referer, validate_stream_url


def resolve_ytdlp_embed(url: str, *, name: str, priority: int, ok, warn) -> list[dict]:
    if not shutil.which("yt-dlp"):
        warn(f"[{name}] yt-dlp not found, skipping embed")
        return []
    attempts = 3 if is_dailymotion_url(url) else 1
    command = ["yt-dlp", "-j", "--no-warnings", url]
    data = None
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            output = read_bounded_process_stdout(process, timeout=20)
            if process.returncode != 0:
                last_error = f"yt-dlp exited with {process.returncode}"
                continue
            data = json.loads(output)
            break
        except subprocess.TimeoutExpired:
            last_error = "yt-dlp timed out"
        except Exception as exc:
            last_error = f"yt-dlp failed: {exc}"
        if attempt < attempts:
            warn(f"[{name}] {last_error}; retrying")
    if data is None:
        if last_error:
            warn(f"[{name}] {last_error}")
        return []

    streams = streams_from_ytdlp_data(data, url=url, name=name, priority=priority)
    if streams:
        ok(f"[{name}] yt-dlp found {len(streams)} stream(s)")
    return streams


def _stream_score(stream: dict) -> tuple[int, int]:
    return int(stream.get("_quality_rank") or 0), int(stream.get("_bitrate") or 0)


def _stream_type(item: dict, stream_url: str) -> str:
    protocol = str(item.get("protocol") or "").casefold()
    manifest_url = str(item.get("manifest_url") or "")
    parsed = urllib.parse.urlparse(str(stream_url or ""))
    query = urllib.parse.unquote(parsed.query).casefold()
    path = urllib.parse.unquote(parsed.path).casefold()
    if "m3u8" in protocol or ".m3u8" in path or ".m3u8" in query or manifest_url:
        return "hls"
    return stream_type_from_url(stream_url)


def _resolution_label(item: dict) -> str:
    resolution = str(item.get("resolution") or "")
    if resolution and resolution != "audio only":
        return resolution
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width and height and width >= 1000 and height < 720:
        return f"{width}x{height}"
    if height:
        return f"{height}p"
    return "Adaptive"


def _is_useful_quality(item: dict) -> bool:
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width and height:
        return width >= 1280
    return height >= 720


def _quality_rank(item: dict) -> int:
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width and height:
        return width * height
    return height


def _bitrate(item: dict) -> int:
    return int(float(item.get("tbr") or item.get("vbr") or item.get("abr") or 0))


def _headers_and_referer(item: dict, data: dict) -> tuple[dict, str]:
    raw_headers = proxy_filtered_headers(
        item.get("http_headers", data.get("http_headers", {}))
    )
    referer = raw_headers.get("Referer", "") or raw_headers.get("referer", "")
    try:
        referer = validate_optional_referer(referer)
    except ValueError:
        referer = ""
    return {}, referer


def _find_best_audio(formats: list[dict]) -> dict | None:
    """Find the best audio-only format."""
    audio_formats = [
        f for f in formats
        if f.get("vcodec") == "none"
        and (
            f.get("acodec") not in (None, "none")
            or f.get("audio_ext") not in (None, "none")
            or f.get("resolution") == "audio only"
        )
        and f.get("url")
    ]
    if not audio_formats:
        return None
    return max(audio_formats, key=lambda f: int(float(f.get("abr") or f.get("tbr") or 0)))


def _is_video_format(item: dict) -> bool:
    """True if this format entry is a video (not audio-only, has video stream)."""
    vcodec = item.get("vcodec")
    acodec = item.get("acodec")
    # explicitly audio-only
    if vcodec == "none":
        return False
    # no codec info and no video_ext — skip (timeline thumbnails etc.)
    video_ext = item.get("video_ext")
    if vcodec is None and video_ext in (None, "none"):
        return bool(item.get("width") or item.get("height"))
    # has acodec but no vcodec/video_ext — pure audio
    if acodec not in (None, "none") and vcodec is None and not video_ext:
        return False
    return True


def _stream_from_format(
        item: dict,
        data: dict,
        *,
        name: str,
        priority: int,
        audio_format: dict | None = None,
        is_dailymotion: bool = False) -> dict | None:
    stream_url = item.get("url")
    if not stream_url:
        return None
    try:
        stream_url = validate_stream_url(stream_url)
    except ValueError:
        return None

    stream_type = _stream_type(item, stream_url)
    headers, referer = _headers_and_referer(item, data)
    resolution = _resolution_label(item)
    label = f"{name} ({resolution})"

    needs_audio = item.get("acodec") == "none"
    stream: dict = {
        "source_name": label,
        "link": stream_url,
        "type": stream_type,
        "resolution": resolution,
        "referer": referer,
        "headers": headers,
        "source_priority": priority,
        "android_safe": not needs_audio and (
            stream_type == "mp4" or (stream_type == "hls" and not (referer or headers))
        ),
        "_quality_rank": _quality_rank(item),
        "_bitrate": _bitrate(item),
    }

    if needs_audio and audio_format:
        try:
            audio_url = validate_stream_url(audio_format.get("url"))
        except ValueError:
            audio_url = None
        if audio_url:
            stream["audio_url"] = audio_url
            stream["android_safe"] = True
            stream["split_video_url"] = stream_url
            stream["split_audio_url"] = audio_url
            stream["split_width"] = item.get("width") or 1280
            stream["split_height"] = item.get("height") or 720
            stream["split_bandwidth"] = item.get("tbr") or item.get("vbr") or 2400
            if is_dailymotion:
                stream["dailymotion_video"] = stream_url
                stream["dailymotion_audio"] = audio_url
                stream["dailymotion_width"] = item.get("width") or 1280
                stream["dailymotion_height"] = item.get("height") or 720
                stream["dailymotion_bandwidth"] = item.get("tbr") or item.get("vbr") or 2400

    return stream


def streams_from_ytdlp_data(data: dict, *, url: str, name: str, priority: int) -> list[dict]:
    formats = data.get("formats", [])
    _is_dm = is_dailymotion_url(url)

    # find best audio-only format once, reuse for any split video format
    best_audio = _find_best_audio(formats) if formats else None

    streams = []
    seen_urls: set[str] = set()

    for item in formats:
        if not _is_video_format(item):
            continue
        if not _is_useful_quality(item):
            continue

        stream = _stream_from_format(
            item,
            data,
            name=name,
            priority=priority,
            audio_format=best_audio if item.get("acodec") == "none" else None,
            is_dailymotion=_is_dm,
        )
        if not stream:
            continue
        link = stream.get("link", "")
        if link in seen_urls:
            continue
        seen_urls.add(link)
        streams.append(stream)

    streams.sort(key=_stream_score, reverse=True)
    return streams
