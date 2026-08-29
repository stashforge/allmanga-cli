"""Watch-history formatting and filtering."""

import time

from .metadata import positive_int
from .titles import get_show_display_title
from .episodes import episode_id_at, episode_index_for_id


def format_relative_time(timestamp, now=None):
    try:
        if not timestamp:
            return ""
        seconds = int((time.time() if now is None else now) - float(timestamp))
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        if seconds < 604800:
            return f"{seconds // 86400}d ago"
        return f"{seconds // 604800}w ago"
    except Exception:
        return ""


def _episode_ids_for_translation(show, translation_type):
    if not show:
        return []
    stored_type = show.get("_episode_ids_ttype")
    if stored_type and stored_type != translation_type:
        return []
    return show.get("_episode_ids") or []

def local_progress(entries, show, translation_type="sub"):
    if not show:
        return None
    show_id = str(show.get("_id") or "")
    if not show_id:
        return None
    from .matching import is_same_show
    for entry in entries:
        entry_show = entry.get("show", {})
        if (
            not is_same_show(entry_show, show)
            or entry.get("translation_type", "sub") != translation_type
        ):
            continue
        episode_id = entry.get("episode", 0)
        if str(episode_id) in ("0", "0.0"):
            return 0
        episode_ids = (
            _episode_ids_for_translation(show, translation_type)
            or _episode_ids_for_translation(entry_show, translation_type)
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
            labels=show.get("_episode_labels"),
        )
        if history_index is None:
            import decimal
            try:
                hist_num = decimal.Decimal(str(history_episode))
                for idx, eid in enumerate(episode_ids):
                    try:
                        if decimal.Decimal(str(eid)) == hist_num:
                            history_index = idx
                            break
                    except decimal.InvalidOperation:
                        continue
            except decimal.InvalidOperation:
                pass
        if history_index is None:
            return episode_id_at(episode_ids, 0)
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
    if show_id and resume_time(show_id, history_episode) > 0:
        return history_episode
    return history_episode + 1

def history_entry_progress(
        entry,
        *,
        prepare_display_state,
        get_local_progress):
    show = entry.get("show", {})
    translation_type = entry.get("translation_type", "sub")
    prepare_display_state(show, translation_type)
    label = "LOCAL"
    raw_val = entry.get("episode")
    from .episodes import clean_episode_identifier
    progress_val = clean_episode_identifier(raw_val) if raw_val else "0"

    import decimal
    try:
        progress_num = decimal.Decimal(str(progress_val))
    except decimal.InvalidOperation:
        progress_num = decimal.Decimal(0)

    available = history_available_episode_count(entry)
    full = history_full_episode_count(entry)

    total = full or available

    if total is not None:
        try:
            total_dec = decimal.Decimal(str(total))
            if progress_num > total_dec:
                total = progress_val
        except decimal.InvalidOperation:
            pass

    return label, progress_val, total


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

    suffix = f" ({translation_type})" if translation_type != "sub" else ""
    return f"{name}{suffix}"


def history_provider_is_completed(show):
    status = str(show.get("status") or "").upper()
    return status in ("COMPLETED", "FINISHED", "ENDED")

def history_available_episode_count(entry):
    from allmanga_cli.domain.episodes import highest_episode_number
    show = entry.get("show", {})
    ttype = entry.get("translation_type", "sub")

    if show.get("_episode_ids_ttype") == ttype:
        ep_ids = show.get("_episode_ids") or []
        if ep_ids:
            return highest_episode_number(ep_ids)

    next_episode = positive_int(show.get("_next_airing_ep"))
    if next_episode:
        return max(0, next_episode - 1)

    avail = (show.get("availableEpisodes") or {}).get(ttype)
    import decimal
    try:
        if avail is not None:
            avail_dec = decimal.Decimal(str(avail))
            if avail_dec >= 0:
                return int(avail_dec) if avail_dec % 1 == 0 else str(avail_dec)
    except decimal.InvalidOperation:
        pass

    return None

def history_full_episode_count(entry):
    show = entry.get("show", {})
    try:
        count = int(show.get("episodeCount"))
        if count > 0:
            return count
    except (TypeError, ValueError):
        pass
    return history_available_episode_count(entry)

def history_entry_category(
        entry,
        *,
        prepare_display_state,
        get_local_progress):
    show = entry.get("show", {})

    _, local_progress, _ = history_entry_progress(
        entry,
        prepare_display_state=prepare_display_state,
        get_local_progress=get_local_progress,
    )

    import decimal
    try:
        local_num = decimal.Decimal(str(local_progress))
    except decimal.InvalidOperation:
        local_num = decimal.Decimal(0)

    available_count = history_available_episode_count(entry)
    full_count = history_full_episode_count(entry)
    provider_completed = history_provider_is_completed(show)

    target_count = full_count if provider_completed else available_count
    try:
        target_dec = decimal.Decimal(str(target_count)) if target_count is not None else None
    except decimal.InvalidOperation:
        target_dec = None

    if provider_completed:
        if target_dec is not None and local_num >= target_dec:
            return "Completed"
        return "Active"

    if target_dec is not None:
        if local_num < target_dec:
            return "Active"
        return "Up to date"

    return "Active"

def filter_history_entries(
        history,
        mode,
        *,
        prepare_display_state,
        get_local_progress):
    mode = str(mode or "Active").capitalize()
    if mode == "Up To Date":
        mode = "Up to date"
    if mode == "All":
        return list(history)

    return [
        entry
        for entry in history
        if history_entry_category(
            entry,
            prepare_display_state=prepare_display_state,
            get_local_progress=get_local_progress,
        ) == mode
    ]
