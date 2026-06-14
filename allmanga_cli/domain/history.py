"""Watch-history formatting and filtering."""

import time

from .metadata import positive_int
from .titles import get_show_display_title


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
