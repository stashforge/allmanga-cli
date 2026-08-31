"""Desktop mpv playback orchestration."""

from ..media.proxy_rules import proxy_filtered_headers
from ..media.urls import validate_optional_referer, validate_stream_url


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
        next_episode=None,
        mal_id=None,
        aniskip_enabled=True,
        aniskip_auto=True):
    url = validate_stream_url(stream["link"])
    audio_url = (
        validate_stream_url(stream["audio_url"])
        if stream.get("audio_url")
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
    from allmanga_cli.domain.episodes import episode_label, clean_episode_identifier, episode_progress_number
    raw_ep = str(episode_label(episode)).strip()
    ep_str = clean_episode_identifier(raw_ep) or raw_ep
    
    if ep_str.lower() in ("movie", "full"):
        media_title = f"{title} ({resolution})"
    else:
        if ep_str and ep_str[0].isdigit():
            ep_str = f"EP {ep_str}"
        elif ep_str.lower() == "ova":
            ep_str = "OVA"
        elif ep_str.lower().startswith("ova "):
            ep_str = "OVA " + ep_str[4:]
        else:
            ep_str = ep_str.title()
        media_title = f"{title} - {ep_str} ({resolution})"

    start_time = (
        get_resume_time(show_id, episode)
        or get_resume_time(show_id, ep_str)
        or get_resume_time(show_id, raw_ep)
    ) if show_id else 0
    resume_message = (
        f"Resuming at {int(start_time // 60):02d}:"
        f"{int(start_time % 60):02d}"
    )
    osd_msg = (
        f"{osd_msg}\n{resume_message}" if (osd_msg and start_time > 0) else (resume_message if start_time > 0 else osd_msg)
    )


    skip_intervals = []
    if aniskip_enabled and mal_id:
        try:
            from ..media.aniskip import fetch_skip_times
            ep_num = episode_progress_number(episode)
            skip_intervals = fetch_skip_times(mal_id, ep_num)
        except Exception:
            skip_intervals = []

    ipc_player.load(
        url,
        media_title,
        headers,
        referer,
        start_time,
        osd_msg,
        audio_url,
        subtitle_url,
        skip_intervals=skip_intervals,
        aniskip_auto=aniskip_auto,
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
