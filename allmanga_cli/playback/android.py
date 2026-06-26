"""Android player discovery and intent launching."""

import subprocess

from ..media.dailymotion import build_dailymotion_hls_manifest
from ..media.dash import generate_dash_mpd
from ..media.local_proxy import (
    cleanup_active_local_proxy,
    replace_active_local_proxy,
    start_local_content_server,
    start_local_proxy,
)
from ..media.proxy_rules import proxy_filtered_headers
from ..media.urls import validate_optional_referer, validate_stream_url


PLAYERS = {
    "mpv": ("is.xyz.mpv", "is.xyz.mpv.MPVActivity"),
    "mpvex": (
        "app.marlboroadvance.mpvex",
        ".ui.player.PlayerActivity",
    ),
    "vlc": (
        "org.videolan.vlc",
        "org.videolan.vlc.gui.video.VideoPlayerActivity",
    ),
    "next": (
        "dev.anilbeesetti.nextplayer",
        ".feature.player.PlayerActivity",
    ),
}

_packages = None
_info = lambda message: None
_ok = lambda message: None
_warn = lambda message: None
_error = lambda message: None


def configure_reporters(info, ok, warn, error):
    global _info, _ok, _warn, _error
    _info = info
    _ok = ok
    _warn = warn
    _error = error


def package_installed(package):
    global _packages
    if _packages is None:
        try:
            _packages = subprocess.run(
                ["pm", "list", "packages"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
        except Exception:
            _packages = ""
    return f"package:{package}" in _packages


def play_android(
        title,
        episode,
        stream,
        fetch_callback,
        player="mpv",
        total_eps=1,
        show_id=None,
        is_binge=False):
    del fetch_callback, total_eps, show_id, is_binge
    try:
        url = validate_stream_url(stream["link"])
        referer = validate_optional_referer(stream.get("referer", ""))
    except ValueError:
        _error("Player rejected an unsafe stream URL.")
        return False

    headers = proxy_filtered_headers(stream.get("headers", {}))
    package, activity = PLAYERS.get(player, PLAYERS["mpv"])
    media_title = f"{title} - Episode {episode}"
    proxy_server = None
    intent_type = "video/*"

    cleanup_active_local_proxy()
    if stream.get("dash_video") and stream.get("dash_audio"):
        _info(f"{player}: preparing DASH video and audio...")
        try:
            manifest = generate_dash_mpd(
                stream["dash_video"],
                stream["dash_audio"],
                stream.get("dash_duration"),
            )
            url, proxy_server = start_local_content_server(
                manifest,
                "stream.mpd",
                "application/dash+xml",
            )
            replace_active_local_proxy(proxy_server)
            intent_type = "application/dash+xml"
        except Exception as exc:
            _error(f"Could not prepare DASH stream: {exc}")
            return False
    elif (
            stream.get("split_video_url")
            and stream.get("split_audio_url")
            and stream.get("type") == "hls"):
        _info(f"{player}: preparing video and audio...")
        try:
            manifest = build_dailymotion_hls_manifest(
                stream["split_video_url"],
                stream["split_audio_url"],
                width=stream.get("split_width") or 1280,
                height=stream.get("split_height") or 720,
                bandwidth=int(float(stream.get("split_bandwidth") or 2400) * 1000),
            )
            url, proxy_server = start_local_content_server(
                manifest,
                "stream.m3u8",
                "application/vnd.apple.mpegurl",
            )
            replace_active_local_proxy(proxy_server)
            intent_type = "application/vnd.apple.mpegurl"
        except Exception as exc:
            _error(f"Could not prepare split audio stream: {exc}")
            return False
    elif stream.get("dailymotion_video") and stream.get("dailymotion_audio"):
        _info(f"{player}: preparing Dailymotion video and audio...")
        try:
            manifest = build_dailymotion_hls_manifest(
                stream["dailymotion_video"],
                stream["dailymotion_audio"],
                width=stream.get("dailymotion_width") or 1280,
                height=stream.get("dailymotion_height") or 720,
                bandwidth=int(float(stream.get("dailymotion_bandwidth") or 2400) * 1000),
            )
            url, proxy_server = start_local_content_server(
                manifest,
                "stream.m3u8",
                "application/vnd.apple.mpegurl",
            )
            replace_active_local_proxy(proxy_server)
            intent_type = "application/vnd.apple.mpegurl"
        except Exception as exc:
            _error(f"Could not prepare Dailymotion stream: {exc}")
            return False
    elif referer or headers:
        _warn(f"{player}: starting local HTTP proxy for stream headers...")
        try:
            url, proxy_server = start_local_proxy(
                url,
                referer,
                headers,
                stream_type=stream.get("type", "mp4"),
            )
            replace_active_local_proxy(proxy_server)
        except Exception as exc:
            _error(f"Could not start local stream proxy: {exc}")
            return False

    _info(f"Opening {media_title} in {player}...")
    command = [
        "am",
        "start",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        url,
        "-t",
        intent_type,
        "-n",
        f"{package}/{activity}",
        "--es",
        "title",
        media_title,
    ]

    launched = False
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            _ok(f"{player} opened.")
            launched = True
        else:
            _error(f"Could not open {player}.")
    except Exception as exc:
        _error(f"Could not open {player}: {exc}")
    if not launched and proxy_server is not None:
        cleanup_active_local_proxy()
    return launched
