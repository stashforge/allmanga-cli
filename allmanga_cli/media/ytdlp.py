"""yt-dlp based embed extraction."""

from __future__ import annotations

import json
import shutil
import subprocess

from ..core.processes import read_bounded_process_stdout
from .dailymotion import is_dailymotion_url, select_dailymotion_av_pair, stream_type_from_url
from .proxy_rules import proxy_filtered_headers
from .urls import validate_optional_referer, validate_stream_url


def resolve_ytdlp_embed(url: str, *, name: str, priority: int, ok, warn) -> list[dict]:
    if not shutil.which("yt-dlp"):
        warn(f"[{name}] yt-dlp not found, skipping embed")
        return []
    try:
        process = subprocess.Popen(
            ["yt-dlp", "-j", "--no-warnings", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        output = read_bounded_process_stdout(process, timeout=20)
        if process.returncode != 0:
            return []
        data = json.loads(output)
    except subprocess.TimeoutExpired:
        warn(f"[{name}] yt-dlp timed out")
        return []
    except Exception as exc:
        warn(f"[{name}] yt-dlp failed: {exc}")
        return []

    streams = streams_from_ytdlp_data(data, url=url, name=name, priority=priority)
    if streams:
        ok(f"[{name}] yt-dlp found {len(streams)} stream(s)")
    return streams


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
            stream_type = stream_type_from_url(stream_url)
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
                "type": stream_type,
                "resolution": f"{height}p" if height else "Adaptive",
                "referer": referer,
                "headers": headers,
                "source_priority": priority,
                "android_safe": stream_type == "mp4" or (
                    stream_type == "hls" and bool(referer or headers)
                ),
            })
    else:
        stream_url = data.get("url")
        if stream_url:
            try:
                stream_url = validate_stream_url(stream_url)
            except ValueError:
                stream_url = ""
            if stream_url:
                stream_type = stream_type_from_url(stream_url)
                streams.append({
                    "source_name": name,
                    "link": stream_url,
                    "type": stream_type,
                    "resolution": "Adaptive",
                    "referer": "",
                    "headers": {},
                    "source_priority": priority,
                    "android_safe": stream_type == "mp4",
                })
    return streams
