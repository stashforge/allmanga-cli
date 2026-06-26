"""yt-dlp based embed extraction."""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse

from ..core.processes import read_bounded_process_stdout
from .dailymotion import is_dailymotion_url, select_dailymotion_av_pair, stream_type_from_url
from .proxy_rules import proxy_filtered_headers
from .urls import validate_optional_referer, validate_stream_url


def resolve_ytdlp_embed(url: str, *, name: str, priority: int, ok, warn) -> list[dict]:
    if not shutil.which("yt-dlp"):
        warn(f"[{name}] yt-dlp not found, skipping embed")
        return []
    attempts = 3 if is_dailymotion_url(url) else 1
    data = None
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            process = subprocess.Popen(
                ["yt-dlp", "-j", "--no-warnings", "-f", "b", url],
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
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width and height and width >= 1000 and height and height < 720:
        return f"{width}x{height}"
    if height:
        return f"{height}p"
    return str(item.get("resolution") or "Adaptive")


def _quality_rank(item: dict) -> int:
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width and height:
        return width * height
    return height


def _bitrate(item: dict) -> int:
    return int(float(item.get("tbr") or item.get("vbr") or item.get("abr") or 0))


def _headers_and_referer(item: dict, data: dict) -> tuple[dict, str]:
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
    return headers, referer


def _stream_from_format(
        item: dict,
        data: dict,
        *,
        name: str,
        priority: int,
        best: bool = False) -> dict | None:
    stream_url = item.get("url")
    if not stream_url:
        return None
    if item.get("acodec") == "none" and item.get("vcodec") == "none":
        return None
    try:
        stream_url = validate_stream_url(stream_url)
    except ValueError:
        return None
    stream_type = _stream_type(item, stream_url)
    headers, referer = _headers_and_referer(item, data)
    resolution = _resolution_label(item)
    label = f"{name} Best ({resolution})" if best else f"{name} ({resolution})"
    return {
        "source_name": label,
        "link": stream_url,
        "type": stream_type,
        "resolution": resolution,
        "referer": referer,
        "headers": headers,
        "source_priority": priority,
        "android_safe": stream_type == "mp4" or (
            stream_type == "hls" and bool(referer or headers)
        ),
        "_quality_rank": _quality_rank(item),
        "_bitrate": _bitrate(item),
    }


def _is_useful_variant(stream: dict) -> bool:
    resolution = str(stream.get("resolution") or "")
    if "x" in resolution:
        width = int(resolution.split("x", 1)[0] or 0)
        return width >= 1280
    return int(stream.get("_quality_rank") or 0) >= 1280 * 720


def streams_from_ytdlp_data(data: dict, *, url: str, name: str, priority: int) -> list[dict]:
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
                    "audio_url": audio_url,
                    "dailymotion_video": video_url,
                    "dailymotion_audio": audio_url,
                    "dailymotion_width": video.get("width") or 1280,
                    "dailymotion_height": video.get("height") or 720,
                    "dailymotion_bandwidth": video.get("tbr") or video.get("vbr") or 2400,
                })
    if not is_dailymotion_url(url):
        best_stream = _stream_from_format(
            data,
            data,
            name=name,
            priority=priority,
            best=True,
        )
        if best_stream:
            streams.append(best_stream)
    if formats and not (streams and is_dailymotion_url(url)):
        candidates = [
            stream
            for item in formats
            if (stream := _stream_from_format(item, data, name=name, priority=priority))
        ]
        useful = [stream for stream in candidates if _is_useful_variant(stream)]
        for stream in useful or candidates:
            if not any(existing.get("link") == stream.get("link") for existing in streams):
                streams.append(stream)
    streams.sort(key=_stream_score, reverse=True)
    return streams
