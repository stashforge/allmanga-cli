"""Desktop mpv playback orchestration."""

from ..media.dailymotion import build_dailymotion_hls_manifest
from ..media.local_proxy import start_local_content_server, stop_local_proxy
from ..media.proxy_rules import proxy_filtered_headers
from ..media.urls import validate_optional_referer, validate_stream_url


def _prepare_dailymotion_manifest(stream):
    if not (stream.get("dailymotion_video") and stream.get("dailymotion_audio")):
        return "", None
    manifest = build_dailymotion_hls_manifest(
        validate_stream_url(stream["dailymotion_video"]),
        validate_stream_url(stream["dailymotion_audio"]),
        width=stream.get("dailymotion_width") or 1280,
        height=stream.get("dailymotion_height") or 720,
        bandwidth=int(float(stream.get("dailymotion_bandwidth") or 2400) * 1000),
    )
    return start_local_content_server(
        manifest,
        "stream.m3u8",
        "application/vnd.apple.mpegurl",
    )


def play_desktop(
        ipc_player,
        title,
        episode,
        stream,
        *,
        get_resume_time,
        get_preferred_mirror,
        update_stream_info,
        fetch_callback=None,
        total_eps=1,
        is_binge=False,
        show_id=None,
        osd_msg="",
        episode_index=0,
        next_episode=None):
    url = validate_stream_url(stream["link"])
    proxy_server = None
    dailymotion_url, proxy_server = _prepare_dailymotion_manifest(stream)
    if dailymotion_url:
        url = dailymotion_url
    audio_url = (
        validate_stream_url(stream["audio_url"])
        if stream.get("audio_url") and not dailymotion_url
        else ""
    )
    subtitle_url = (
        validate_stream_url(stream["subtitle_url"])
        if stream.get("subtitle_url")
        else ""
    )
    referer = validate_optional_referer(stream.get("referer", ""))
    headers = proxy_filtered_headers(stream.get("headers", {}))
    resolution = stream.get("resolution", "Adaptive")
    media_title = f"{title} - Episode {episode} ({resolution})"

    start_time = get_resume_time(show_id, episode) if show_id else 0
    resume_message = (
        f"Resuming at {int(start_time // 60):02d}:"
        f"{int(start_time % 60):02d}"
    )
    osd_msg = (
        f"{osd_msg}\n{resume_message}" if osd_msg else resume_message
    )
    try:
        ipc_player.load(
            url,
            media_title,
            headers,
            referer,
            start_time,
            osd_msg,
            audio_url,
            subtitle_url,
        )

        mirror_name = stream.get("source_name", "Unknown")
        preference = get_preferred_mirror(show_id) if show_id else {}
        stream_info = {
            "title": title,
            "mirror": mirror_name,
            "quality": resolution,
            "is_pref": (
                preference.get("source_name") == mirror_name
                and preference.get("resolution") == resolution
            ),
            "episode_index": episode_index,
            "next_episode": next_episode,
        }
        update_stream_info(stream_info)
        result, played_seconds = ipc_player.wait_for_playback(
            stream_info,
            episode,
            total_eps,
            fetch_callback,
            is_binge,
        )
        return (
            result,
            ipc_player.props.get("percent-pos", 0) or 0,
            ipc_player.props.get("playback-time", 0) or 0,
            ipc_player.props.get("duration", 0) or 0,
            played_seconds,
        )
    finally:
        stop_local_proxy(proxy_server)
