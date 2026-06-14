"""Watch-history formatting and filtering."""

import time

from .metadata import positive_int
from .titles import get_show_display_title
from .episodes import episode_id_at, episode_index_for_id


def local_progress(entries, show, translation_type="sub"):
    if not show:
        return None
    show_id = str(show.get("_id") or "")
    if not show_id:
        return None
    for entry in entries:
        entry_show = entry.get("show", {})
        if (
            str(entry_show.get("_id") or "") != show_id
            or entry.get("translation_type", "sub") != translation_type
        ):
            continue
        episode_id = entry.get("episode", 0)
        if str(episode_id) in ("0", "0.0"):
            return 0
        episode_ids = (
            show.get("_episode_ids")
            or entry_show.get("_episode_ids")
            or []
        )
        if episode_ids:
            index = episode_index_for_id(
                [str(episode) for episode in episode_ids],
                episode_id,
            )
            return index + 1 if index is not None else None
        try:
            return max(0, int(float(str(episode_id))))
        except (TypeError, ValueError):
            return None
    return None


def playback_episode(
        entry,
        *,
        translation_type=None,
        episode_ids,
        resume_time):
    show = entry.get("show", {})
    show_id = show.get("_id")
    history_episode = entry.get("episode", 1)
    selected_type = (
        translation_type
        or entry.get("translation_type", "sub")
    )
    if episode_ids:
        if str(history_episode) in ("0", "0.0"):
            return episode_id_at(episode_ids, 0)
        history_index = episode_index_for_id(
            episode_ids,
            history_episode,
        )
        if history_index is None:
            return None
        if show_id and resume_time(show_id, history_episode) > 0:
            return episode_id_at(episode_ids, history_index)
        return episode_id_at(
            episode_ids,
            min(history_index + 1, len(episode_ids) - 1),
        )

    try:
        history_episode = max(1, int(float(str(history_episode))))
    except (TypeError, ValueError):
        history_episode = 1
    total = show.get("availableEpisodes", {}).get(selected_type, 0)
    try:
        total = int(total) if total else 0
    except (TypeError, ValueError):
        total = 0
    if show_id and resume_time(show_id, history_episode) > 0:
        return min(history_episode, total) if total else history_episode
    next_episode = history_episode + 1
    return min(next_episode, total) if total else next_episode


def history_entry_progress(
        entry,
        *,
        prepare_display_state,
        get_local_progress):
    show = entry.get("show", {})
    translation_type = entry.get("translation_type", "sub")
    prepare_display_state(show, translation_type)
    if show.get("_sync_enabled") and show.get("_anilist_progress") is not None:
        label = "AL"
        progress = positive_int(show.get("_anilist_progress"))
        if progress is None:
            progress = 0
    else:
        label = "LOCAL"
        progress = get_local_progress(show, translation_type)
        if progress is None:
            progress = positive_int(entry.get("episode")) or 0

    total = positive_int(show.get("episodeCount"))
    if not total:
        total = len(show.get("_episode_ids") or []) or None
    if not total:
        total = positive_int(
            (show.get("availableEpisodes") or {}).get(translation_type)
        )
    return label, progress, total


def format_history_entry(
        entry,
        *,
        prepare_display_state,
        get_local_progress,
        now=None):
    show = entry.get("show", {})
    translation_type = entry.get("translation_type", "sub")
    prepare_display_state(show, translation_type)
    name = get_show_display_title(show, "?")
    label, progress, total = history_entry_progress(
        entry,
        prepare_display_state=prepare_display_state,
        get_local_progress=get_local_progress,
    )

    ago = ""
    timestamp = entry.get("timestamp", 0)
    try:
        if timestamp:
            seconds = int((time.time() if now is None else now) - float(timestamp))
            if seconds < 60:
                ago = "just now"
            elif seconds < 3600:
                ago = f"{seconds // 60}m ago"
            elif seconds < 86400:
                ago = f"{seconds // 3600}h ago"
            elif seconds < 604800:
                ago = f"{seconds // 86400}d ago"
            else:
                ago = f"{seconds // 604800}w ago"
    except Exception:
        pass

    suffix = f" ({translation_type})" if translation_type != "sub" else ""
    progress_text = f"{progress}/{total}" if total else str(progress)
    authority = "AL " if label == "AL" else ""
    prefix = f"{authority}EP {progress_text}{suffix}"
    if ago:
        prefix = f"{prefix} \u2022 {ago}"
    return f"{prefix}  {name}"


def history_entry_is_completed(
        entry,
        *,
        prepare_display_state,
        get_local_progress):
    show = entry.get("show", {})
    if str(show.get("status") or "").upper() == "RELEASING":
        return False
    _, watched, total = history_entry_progress(
        entry,
        prepare_display_state=prepare_display_state,
        get_local_progress=get_local_progress,
    )
    return bool(total and watched >= total)


def filter_history_entries(
        history,
        mode,
        *,
        prepare_display_state,
        get_local_progress):
    mode = str(mode or "Active").title()
    if mode == "All":
        return list(history)
    want_completed = mode == "Completed"
    return [
        entry
        for entry in history
        if history_entry_is_completed(
            entry,
            prepare_display_state=prepare_display_state,
            get_local_progress=get_local_progress,
        ) == want_completed
    ]
