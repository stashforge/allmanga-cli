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


def format_ep_progress(label, progress, total, local_only=False):
    import decimal as _dec
    try:
        p = _dec.Decimal(str(progress))
        if p < 0:
            p = _dec.Decimal(0)
        # Display as int when whole, preserve decimal string otherwise
        progress = int(p) if p == p.to_integral_value() else str(p.normalize())
    except (_dec.InvalidOperation, TypeError, ValueError):
        return ""
    prefix = f"\033[38;5;244mEP{DIM}"
    return f"{prefix} {progress}/{total}" if total else f"{prefix} {progress}"


def format_progress(anime, local_only=False, ttype="sub"):
    from allmanga_cli.domain.history import history_available_episode_count, history_full_episode_count
    entry = {"show": anime, "translation_type": ttype}
    available = history_available_episode_count(entry)
    full = history_full_episode_count(entry)

    total = full or available

    local_progress = anime.get("_local_progress")
    local_label = anime.get("_local_episode_label")
    if not local_label:
        local_label = local_progress

    import decimal
    try:
        local_num = decimal.Decimal(str(local_label))
    except decimal.InvalidOperation:
        local_num = decimal.Decimal(0)

    if total is not None:
        try:
            total_dec = decimal.Decimal(str(total))
            if local_num > total_dec:
                total = local_label
        except decimal.InvalidOperation:
            pass

    if not local_only:
        sync_enabled = bool(anime.get("_sync_enabled"))
        anilist_progress = anime.get("_anilist_progress")
        authority = anime.get("_progress_authority")
        if anime.get("_sync_conflict") and local_progress is not None:
            return format_ep_progress("LOCAL", local_label, total, local_only)
        if sync_enabled and anilist_progress is not None:
            return format_ep_progress("AL", anilist_progress, total, local_only)
        if authority == "AL" and anilist_progress is not None:
            return format_ep_progress("AL", anilist_progress, total, local_only)
    if local_progress is not None:
        return format_ep_progress("LOCAL", local_label, total, local_only)
    return ""


def format_available_episodes(anime, ttype="sub", local_only=False):
    from allmanga_cli.domain.history import history_available_episode_count, history_full_episode_count
    if str(anime.get("status") or "").upper() != "RELEASING":
        return ""

    next_episode = positive_int(anime.get("_next_airing_ep"))
    if next_episode:
        available_count = max(0, next_episode - 1)
        if local_only:
            entry = {"show": anime, "translation_type": ttype}
            full = history_full_episode_count(entry)
            if full and available_count >= full:
                return ""
        return f"Avail {available_count}"

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
        return f"Next EP {episode} aired"
    return f"Next EP {episode} in {format_time(remaining)}"


def format_years(start_year, end_year, status=None):
    start_year = positive_int(start_year)
    end_year = positive_int(end_year)
    status = str(status or "").upper()
    if start_year and end_year and start_year != end_year:
        return f"{start_year} - {end_year}"
    if start_year:
        if status == "RELEASING":
            return f"{start_year} -"
        return str(start_year)
    if end_year:
        return str(end_year)
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


def anilist_list_status_label(anime, local_only=False):
    if not local_only:
        show_anilist_status = (
            anime.get("_sync_enabled") or anime.get("_anilist_context")
        )
        anilist_list = (
            str(anime.get("_anilist_list") or "").upper().replace(" ", "_")
            if show_anilist_status
            else ""
        )
        if anilist_list in ("CURRENT", "WATCHING"):
            return f"\033[32mAL WATCHING{DIM}"
        if anilist_list == "COMPLETED":
            return f"\033[36mAL COMPLETED{DIM}"
        if anilist_list in ("PLANNING", "PLAN_TO_WATCH"):
            return f"\033[33mAL PLANNING{DIM}"
        if anilist_list == "DROPPED":
            return f"\033[31mAL DROPPED{DIM}"
        if anilist_list == "PAUSED":
            return f"\033[35mAL PAUSED{DIM}"
        if anilist_list in ("REPEATING", "REWATCHING"):
            return f"\033[32mAL REWATCHING{DIM}"
    return ""


def anime_status_label(anime):
    status = str(anime.get("status") or "").upper()
    if status == "RELEASING":
        return f"\033[32mAIRING{DIM}"
    if status == "FINISHED":
        return f"\033[36mFINISHED{DIM}"
    if status in ("NOT_YET_RELEASED", "NOT YET RELEASED"):
        return f"\033[33mUPCOMING{DIM}"
    if status == "CANCELLED":
        return f"\033[31mCANCELLED{DIM}"
    if status == "HIATUS":
        return f"\033[35mHIATUS{DIM}"
    return ""


def anilist_status_label(anime, local_only=False):
    return anilist_list_status_label(anime, local_only=local_only) or anime_status_label(anime)


def format_info_metadata_line(
    anime,
    ttype="sub",
    now=None,
    override_ep_str=None,
    local_only=False,
):
    details = []
    anilist_label = anilist_list_status_label(anime, local_only=local_only)
    media_status_label = anime_status_label(anime)
    if override_ep_str:
        progress = f"\033[38;5;244mEP{DIM} {override_ep_str}"
    else:
        progress = format_progress(anime, local_only=local_only, ttype=ttype)

    available = format_available_episodes(anime, ttype, local_only=local_only)
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

    if anilist_label:
        details.append(anilist_label)
    if media_status_label:
        details.append(media_status_label)
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
