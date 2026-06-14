"""Anime progress, airing, year, and metadata-line formatting."""

import time


DIM = "\033[38;5;248m"


def format_time(secs):
    if not secs:
        return ""
    days, seconds = divmod(secs, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    pieces = []
    if days > 0:
        pieces.append(f"{int(days)}d")
    if hours > 0:
        pieces.append(f"{int(hours)}h")
    if minutes > 0 and len(pieces) < 2:
        pieces.append(f"{int(minutes)}m")
    return " ".join(pieces[:2])


def set_next_airing_fields(show, next_air):
    if not show or not next_air:
        return
    show["_next_airing_ep"] = next_air.get("episode")
    remaining = next_air.get("timeUntilAiring")
    show["_next_airing_time"] = remaining
    try:
        show["_next_airing_at"] = int(time.time()) + int(remaining)
    except (TypeError, ValueError):
        pass


def positive_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def format_ep_progress(label, progress, total):
    try:
        progress = max(0, int(progress))
    except (TypeError, ValueError):
        return ""
    label_color = "\033[36m" if label == "AL" else "\033[38;5;244m"
    prefix = f"{label_color}{label}{DIM} EP"
    return f"{prefix} {progress}/{total}" if total else f"{prefix} {progress}"


def format_progress(anime):
    total = positive_int(anime.get("episodeCount"))
    sync_enabled = bool(anime.get("_sync_enabled"))
    local_progress = anime.get("_local_progress")
    anilist_progress = anime.get("_anilist_progress")
    authority = anime.get("_progress_authority")
    if anime.get("_sync_conflict") and local_progress is not None:
        return format_ep_progress("LOCAL", local_progress, total)
    if sync_enabled and anilist_progress is not None:
        return format_ep_progress("AL", anilist_progress, total)
    if authority == "AL" and anilist_progress is not None:
        return format_ep_progress("AL", anilist_progress, total)
    if local_progress is not None:
        return format_ep_progress("LOCAL", local_progress, total)
    return ""


def format_available_episodes(anime, ttype="sub"):
    if str(anime.get("status") or "").upper() != "RELEASING":
        return ""

    next_episode = positive_int(anime.get("_next_airing_ep"))
    if next_episode:
        return f"Avail {max(0, next_episode - 1)}"

    available = anime.get("availableEpisodes", {}).get(ttype)
    try:
        available = int(available)
    except (TypeError, ValueError):
        available = None
    if available is not None and available >= 0:
        return f"Avail {available}"

    try:
        progress = max(0, int(anime.get("_anilist_progress") or 0))
    except (TypeError, ValueError):
        progress = 0
    return f"Avail {progress}"


def format_next_airing(anime, now=None):
    episode = anime.get("_next_airing_ep")
    airing_at = anime.get("_next_airing_at")
    if not episode or not airing_at:
        return ""
    try:
        current_time = time.time() if now is None else now
        remaining = int(float(airing_at)) - int(current_time)
    except (TypeError, ValueError):
        return ""
    if remaining <= 0:
        return f"EP {episode} aired"
    return f"EP {episode} in {format_time(remaining)}"


def format_years(start_year, end_year, status=None):
    start_year = positive_int(start_year)
    end_year = positive_int(end_year)
    status = str(status or "").upper()
    if start_year and end_year and start_year != end_year:
        return f"{start_year} - {end_year}"
    if start_year and end_year == start_year:
        return str(start_year)
    if start_year and status == "RELEASING":
        return f"{start_year} -"
    if start_year:
        return str(start_year)
    return "TBA"


def should_refresh_anilist(anime, now=None):
    if str(anime.get("status") or "").upper() != "RELEASING":
        return False
    airing_at = anime.get("_next_airing_at")
    if not airing_at:
        return bool(
            anime.get("_next_airing_ep") or anime.get("_next_airing_time")
        )
    try:
        current_time = time.time() if now is None else now
        return int(float(airing_at)) <= int(current_time)
    except (TypeError, ValueError):
        return True


def anilist_status_label(anime):
    status = str(anime.get("status") or "").upper()
    show_anilist_status = (
        anime.get("_sync_enabled") or anime.get("_anilist_context")
    )
    anilist_list = (
        str(anime.get("_anilist_list") or "").upper().replace(" ", "_")
        if show_anilist_status
        else ""
    )
    if anilist_list in ("CURRENT", "WATCHING"):
        return f"\033[32mWATCHING{DIM}"
    if anilist_list == "COMPLETED":
        return f"\033[36mCOMPLETED{DIM}"
    if anilist_list in ("PLANNING", "PLAN_TO_WATCH"):
        return f"\033[33mPLAN TO WATCH{DIM}"
    if anilist_list == "DROPPED":
        return f"\033[31mDROPPED{DIM}"
    if anilist_list == "PAUSED":
        return f"\033[35mPAUSED{DIM}"
    if anilist_list in ("REPEATING", "REWATCHING"):
        return f"\033[32mREWATCHING{DIM}"
    if status == "RELEASING":
        return f"\033[32mAIRING{DIM}"
    return ""


def format_info_metadata_line(
    anime,
    ttype="sub",
    now=None,
    override_ep_str=None,
):
    details = []
    status_label = anilist_status_label(anime)
    if override_ep_str:
        label = "AL" if anime.get("_sync_enabled") else "LOCAL"
        label_color = "\033[36m" if label == "AL" else "\033[38;5;244m"
        progress = f"{label_color}{label}{DIM} {override_ep_str}"
    else:
        progress = format_progress(anime)

    available = format_available_episodes(anime, ttype)
    next_airing = format_next_airing(anime, now)
    anime_type = str(anime.get("type") or "TV").upper()
    aired_start = anime.get("airedStart") or {}
    aired_end = anime.get("airedEnd") or {}
    years = format_years(
        aired_start.get("year"),
        aired_end.get("year"),
        anime.get("status"),
    )
    score = anime.get("score")
    score_text = f"★ {score}" if score else "★ -"

    if status_label:
        details.append(status_label)
    if progress:
        details.append(progress)
    if available:
        details.append(available)
    if next_airing:
        details.append(f"\033[38;5;220m{next_airing}{DIM}")
    if anime_type:
        details.append(anime_type)
    if years:
        details.append(years)
    details.append(score_text)
    return " • ".join(details)
