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
        airing_at = int(next_air.get("airingAt"))
    except (TypeError, ValueError):
        airing_at = None
    if airing_at:
        show["_next_airing_at"] = airing_at
        return
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
        progress = str(progress).strip()
        if progress.lower().startswith("episode "):
            progress = progress[8:].strip()
        if not progress or progress.lower() == "none":
            return ""
    prefix = f"\033[38;5;244mWatched{DIM}"
    return f"{prefix} {progress}/{total}" if total else f"{prefix} {progress}"


def format_total_episodes(anime, ttype="sub"):
    total = positive_int(anime.get("episodeCount"))
    if not total:
        avail_map = anime.get("availableEpisodes") or {}
        if isinstance(avail_map, dict):
            total = positive_int(avail_map.get(ttype)) or positive_int(avail_map.get("sub")) or positive_int(avail_map.get("dub"))
        if not total:
            total = positive_int(anime.get("_provider_latest"))
    return f"\033[38;5;244mEP{DIM} {total}" if total else ""


def normalize_anilist_list_status(status):
    normalized = str(status or "").upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "WATCHING": "CURRENT",
        "PLAN_TO_WATCH": "PLANNING",
        "REWATCHING": "REPEATING",
    }
    return aliases.get(normalized, normalized)


def format_progress(anime, local_only=False, ttype="sub"):
    total = positive_int(anime.get("episodeCount"))

    local_progress = anime.get("_local_progress")
    local_label = anime.get("_local_episode_label")
    if not local_label:
        local_label = local_progress

    from .episodes import resolve_dual_episode_label, parse_episode_dual_numbers
    dual_lbl = resolve_dual_episode_label(anime, local_label or local_progress)
    if dual_lbl:
        local_label = dual_lbl

    import decimal

    local_prim, local_sec = parse_episode_dual_numbers(str(local_label or ""))
    try:
        local_num = decimal.Decimal(str(local_prim or local_label))
    except (decimal.InvalidOperation, TypeError, ValueError):
        local_num = decimal.Decimal(0)

    # Only adjust total if not a dual-number bracket tag
    if total is not None and not local_sec:
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
        anilist_num = 0
        if anilist_progress is not None:
            try:
                anilist_num = int(float(str(anilist_progress)))
            except (ValueError, TypeError):
                pass

        anilist_context = bool(anime.get("_anilist_context"))
        if (sync_enabled or anilist_context) and anilist_progress is not None:
            if local_num > anilist_num and not local_sec:
                return format_ep_progress("LOCAL", local_label, total, local_only)
            display_p = local_label if local_sec else anilist_progress
            return format_ep_progress("AL", display_p, total, local_only)
        if authority == "AL" and sync_enabled and anilist_progress is not None:
            display_p = local_label if local_sec else anilist_progress
            return format_ep_progress("AL", display_p, total, local_only)
    if local_progress is not None:
        return format_ep_progress("LOCAL", local_label, total, local_only)
    return ""



def format_available_episodes(anime, ttype="sub", local_only=False):
    from allmanga_cli.domain.history import history_available_episode_count, history_full_episode_count
    from .episodes import parse_episode_dual_numbers, clean_episode_identifier

    if str(anime.get("status") or "").upper() != "RELEASING":
        return ""

    eids = anime.get("_episode_ids") or []
    labels = anime.get("_episode_labels") or {}
    sec_tag = None
    first_num = None
    last_num = None

    if eids:
        first_lbl = str(labels.get(eids[0], labels.get(str(eids[0]), eids[0])))
        last_lbl = str(labels.get(eids[-1], labels.get(str(eids[-1]), eids[-1])))
        prim_f, sec_f = parse_episode_dual_numbers(first_lbl)
        prim_l, sec_l = parse_episode_dual_numbers(last_lbl)

        sec_tag = sec_l
        try:
            first_num = int(prim_f or clean_episode_identifier(first_lbl))
            last_num = int(sec_l or prim_l or clean_episode_identifier(last_lbl))
        except (ValueError, TypeError):
            pass

    next_episode = positive_int(anime.get("_next_airing_ep"))
    if next_episode:
        available_count = max(0, next_episode - 1)
        if local_only:
            entry = {"show": anime, "translation_type": ttype}
            full = history_full_episode_count(entry)
            if full and available_count >= full:
                return ""
        if sec_tag:
            return f"Avail {available_count} [{sec_tag}]"
        return f"Avail {available_count}"

    total = positive_int(anime.get("episodeCount"))
    available = anime.get("availableEpisodes", {}).get(ttype) if isinstance(anime.get("availableEpisodes"), dict) else None
    try:
        available = int(available)
    except (TypeError, ValueError):
        available = None

    if not available and eids:
        available = len(eids)

    if available is not None and available > 0:
        if sec_tag:
            return f"Avail {available} [{sec_tag}]"
        if total is not None and available == total:
            return ""
        return f"Avail {available}"

    return ""


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
    if status == "NOT_YET_RELEASED":
        return "TBA"
    return ""


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


def anilist_list_status_label(anime, local_only=False, hide_status=None):
    if not local_only and (anime.get("_sync_enabled") or anime.get("_anilist_context")):
        show_anilist_status = bool(anime.get("_anilist_list"))
        anilist_list = normalize_anilist_list_status(anime.get("_anilist_list")) if show_anilist_status else ""
        if anilist_list and hide_status and anilist_list == normalize_anilist_list_status(hide_status):
            return ""
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
    color = "\033[38;5;250m"
    if status == "RELEASING":
        return f"{color}AIRING{DIM}"
    if status == "FINISHED":
        return f"{color}FINISHED{DIM}"
    if status in ("NOT_YET_RELEASED", "NOT YET RELEASED"):
        return f"{color}UPCOMING{DIM}"
    if status == "CANCELLED":
        return f"{color}CANCELLED{DIM}"
    if status == "HIATUS":
        return f"{color}HIATUS{DIM}"
    return ""


def anilist_status_label(anime, local_only=False, hide_status=None):
    return anilist_list_status_label(
        anime,
        local_only=local_only,
        hide_status=hide_status,
    ) or anime_status_label(anime)


def format_info_metadata_line(
    anime,
    ttype="sub",
    now=None,
    override_ep_str=None,
    local_only=False,
    hide_anilist_status=None,
):
    details = []
    anilist_label = anilist_list_status_label(
        anime,
        local_only=local_only,
        hide_status=hide_anilist_status,
    )
    media_status_label = anime_status_label(anime)
    if override_ep_str:
        if override_ep_str.lower() in ("movie", "full"):
            progress = f"\033[38;5;244m{override_ep_str.title()}{DIM}"
        else:
            progress = f"\033[38;5;244mEP{DIM} {override_ep_str}"
    else:
        progress = format_progress(anime, local_only=local_only, ttype=ttype)
        if not progress:
            progress = format_total_episodes(anime, ttype=ttype)
            
        # For downloads, if we show Watched X/Y where Y is downloaded count,
        # also show the anime's actual total episodes if available.
        if local_only and "originalEpisodeCount" in anime:
            original_total = positive_int(anime.get("originalEpisodeCount"))
            if original_total:
                progress = f"{progress} • \033[38;5;244mEP{DIM} {original_total}"

    available = format_available_episodes(anime, ttype, local_only=local_only)
    next_airing = format_next_airing(anime, now)
    anime_type = str(anime.get("type") or "UNKNOWN").upper()
    if anime_type == "UNKNOWN":
        anime_type = "UNKNOWN TYPE"

    sub_dub_label = str(ttype or "sub").upper()
    def _ext_year(val):
        if isinstance(val, dict): return val.get("year")
        if isinstance(val, str):
            import re
            m = re.search(r'\b(20\d{2}|19\d{2})\b', val)
            return m.group(1) if m else val
        return None

    aired_start = anime.get("airedStart")
    aired_end = anime.get("airedEnd")
    years = format_years(
        _ext_year(aired_start),
        _ext_year(aired_end),
        anime.get("status"),
    )
    score = anime.get("score")
    score_text = f"★ {score}" if score else "★ -"

    if anilist_label:
        details.append(anilist_label)
    if media_status_label:
        details.append(media_status_label)
    if anime_type:
        details.append(anime_type)
    if sub_dub_label:
        details.append(sub_dub_label)
    if progress:
        details.append(progress)
    if available and (not progress or str(available).split()[-1] not in str(progress)):
        details.append(available)
    if next_airing:
        details.append(f"\033[38;5;117m{next_airing}{DIM}")
    if years:
        details.append(years)
    details.append(score_text)
    return " • ".join(details)


def prepare_show_display_state(show, ttype="sub", sync_enabled=None):
    if not show:
        return show
    if "_local_progress" in show and "_sync_enabled" in show and "_progress_authority" in show:
        return show
    from allmanga_cli.context import FLAGS as runtime_flags
    from allmanga_cli.core.storage import get_title_sync, get_local_progress, get_local_episode_label

    if runtime_flags.incognito_mode:
        show["_local_progress"] = None
        show["_local_episode_label"] = None
        show["_sync_enabled"] = False
        show.pop("_anilist_progress", None)
        show.pop("_anilist_list", None)
        show.pop("watched_episodes", None)
        show["_progress_authority"] = "LOCAL"
        return show
    raw_anilist_show = bool(
        show.get("_anilist_list")
        and not show.get("_allanime_name")
        and not show.get("aniListId")
    )
    if raw_anilist_show:
        show["aniListId"] = str(show.get("_id"))
    if runtime_flags.sync_force_off:
        sync_enabled = False
    elif sync_enabled is None and raw_anilist_show:
        sync_enabled = True
    elif sync_enabled is None and runtime_flags.sync_force_on and show.get("aniListId"):
        sync_enabled = True
    elif sync_enabled is None:
        sync_enabled = get_title_sync(show)
    show["_sync_enabled"] = bool(sync_enabled)
    
    if "watched_episodes" in show:
        watched_count = len(show["watched_episodes"])
        show["_local_progress"] = watched_count
        if watched_count > 0:
            def safe_num(x):
                try: return float(x)
                except ValueError: return -1
            show["_local_episode_label"] = max(show["watched_episodes"], key=safe_num)
        else:
            show["_local_episode_label"] = "0"
    else:
        show["_local_progress"] = get_local_progress(show, ttype)
        show["_local_episode_label"] = get_local_episode_label(show, ttype)
        if not show.get("aniListId") and not show.get("_episode_ids"):
            from allmanga_cli.core.storage import get_history_entry
            entry = get_history_entry(show, ttype)
            if entry and isinstance(entry.get("show"), dict):
                hist_show = entry["show"]
                for k in (
                    "altNames",
                    "englishName",
                    "nativeName",
                    "status",
                    "episodeCount",
                    "aniListId",
                    "malId",
                    "score",
                    "genres",
                    "_next_airing_ep",
                    "_next_airing_at",
                    "_next_airing_time",
                    "_episode_ids",
                    "_episode_labels",
                ):
                    if not show.get(k) and hist_show.get(k):
                        show[k] = hist_show[k]
    if not show.get("_progress_authority"):
        show["_progress_authority"] = "AL" if sync_enabled else "LOCAL"
    return show


def batch_prepare_shows_display_state(shows, ttype="sub"):
    """Pre-warm cheap metadata and watch progress for a list of shows in a single in-memory pass."""
    if not shows:
        return shows
    from allmanga_cli.context import FLAGS as runtime_flags
    from allmanga_cli.core.storage import load_history, load_prefs
    from allmanga_cli.domain.matching import is_same_show
    from allmanga_cli.state import preferences as preference_state

    if runtime_flags.incognito_mode:
        for s in shows:
            if isinstance(s, dict):
                prepare_show_display_state(s, ttype)
        return shows

    try:
        history_list = load_history()
    except Exception:
        history_list = []

    try:
        prefs = load_prefs()
    except Exception:
        prefs = {}

    # Build fast O(1) history indexes
    id_to_entry = {}
    al_to_entry = {}
    name_to_entry = {}
    for entry in history_list:
        if not isinstance(entry, dict):
            continue
        es = entry.get("show")
        if not isinstance(es, dict):
            continue
        eid = es.get("_id")
        if eid:
            id_to_entry[str(eid)] = entry
        al_id = es.get("aniListId")
        if al_id:
            al_to_entry[str(al_id)] = entry
        ename = es.get("name")
        if ename:
            name_to_entry[str(ename).strip().lower()] = entry

    for show in shows:
        if not isinstance(show, dict):
            continue
        if "_local_progress" in show:
            continue

        raw_anilist_show = bool(
            show.get("_anilist_list")
            and not show.get("_allanime_name")
            and not show.get("aniListId")
        )
        if raw_anilist_show:
            show["aniListId"] = str(show.get("_id"))

        if runtime_flags.sync_force_off:
            sync_enabled = False
        elif raw_anilist_show or (runtime_flags.sync_force_on and show.get("aniListId")):
            sync_enabled = True
        else:
            sync_pref = preference_state.title_sync_preference(prefs, show)
            sync_enabled = sync_pref is True
        show["_sync_enabled"] = bool(sync_enabled)

        if "watched_episodes" in show:
            watched_count = len(show["watched_episodes"])
            show["_local_progress"] = watched_count
            if watched_count > 0:
                def safe_num(x):
                    try: return float(x)
                    except ValueError: return -1
                show["_local_episode_label"] = max(show["watched_episodes"], key=safe_num)
            else:
                show["_local_episode_label"] = "0"
        else:
            sid = str(show.get("_id") or "")
            sal = str(show.get("aniListId") or "")
            sname = str(show.get("name") or "").strip().lower()

            matched_entry = id_to_entry.get(sid) or al_to_entry.get(sal) or name_to_entry.get(sname)
            if matched_entry is None:
                for entry in history_list:
                    entry_show = entry.get("show")
                    if is_same_show(entry_show, show):
                        matched_entry = entry
                        break

            if matched_entry:
                ep_val = str(matched_entry.get("episode") or "0")
                show["_local_progress"] = 1 if ep_val != "0" else 0
                show["_local_episode_label"] = ep_val
                hist_show = matched_entry.get("show") or {}
                if not show.get("aniListId") and not show.get("_episode_ids"):
                    for k in (
                        "altNames", "englishName", "nativeName", "status", "episodeCount",
                        "aniListId", "malId", "score", "genres", "_next_airing_ep",
                        "_next_airing_at", "_next_airing_time", "_episode_ids", "_episode_labels"
                    ):
                        if not show.get(k) and hist_show.get(k):
                            show[k] = hist_show[k]
            else:
                show["_local_progress"] = 0
                show["_local_episode_label"] = "0"

        if not show.get("_progress_authority"):
            show["_progress_authority"] = "AL" if sync_enabled else "LOCAL"

    return shows


def apply_provider_metadata_to_history_show(show, provider_show):
    changed = False

    for key in ("status", "episodeCount", "airedStart", "score", "type", "season"):
        val = provider_show.get(key)
        if val is not None and str(show.get(key)) != str(val):
            show[key] = val
            changed = True

    for key in ("thumbnail", "name", "englishName", "nativeName"):
        val = provider_show.get(key)
        if val and not show.get(key):
            show[key] = val
            changed = True

    avail = provider_show.get("availableEpisodes")
    if avail and isinstance(avail, dict):
        current_avail = show.get("availableEpisodes") or {}
        if current_avail != avail:
            show["availableEpisodes"] = dict(avail)
            changed = True

    return changed


apply_allanime_metadata_to_history_show = apply_provider_metadata_to_history_show



