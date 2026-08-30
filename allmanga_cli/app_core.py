#!/usr/bin/env python3
"""
allmanga-cli — Terminal anime stream player (AllAnime / AllManga)
"""

import sys, shutil, threading, os, re, json, time
import hashlib, subprocess
import tty, termios, select, signal, atexit, tempfile, getpass, traceback
from datetime import date
from typing import Optional

from allmanga_cli.core.api import (
    MAX_API_JSON_BYTES,
    ProviderDependencyError,
    SearchFailure,
    anilist_account_cache_key,
    read_json_response,
    read_limited_response,
    search_failure_message,
)
from allmanga_cli.cli.args import (
    build_anilist_search_parser,
    build_command_parser,

    parse_cli_args,
)
from allmanga_cli.cli.completion import generate_completion, install_completion
from allmanga_cli.ui.picker import tui_pick
from allmanga_cli.media.download import download_episode
from allmanga_cli.media.dash import generate_dash_mpd, resolve_dash_raw_urls
from allmanga_cli.media.library import (
    natural_key as _natural_key,
    scan_download_library,
)
from allmanga_cli.media import local_proxy
from allmanga_cli.media import resolver as stream_resolver
from allmanga_cli.domain.episodes import (
    episode_id_at,
    episode_index_for_id,
    episode_label,
    episode_progress_number,
    is_contiguous_legacy_catalog as _is_contiguous_legacy_catalog,
    normalize_episode_ids as _normalize_episode_ids,
)
from allmanga_cli.domain import history as history_domain
from allmanga_cli.domain import reconciliation as reconciliation_domain
from allmanga_cli.domain.matching import (
    best_allanime_match as _best_allanime_match,
    choose_confident_match as _choose_confident_match,
    explicit_season_number as _explicit_season_number,
    match_score_details as _match_score_details,
    match_titles as _match_titles,
    normalized_match_title as _normalized_match_title,
    score_match,
    title_match_score as _title_match_score,
)
from allmanga_cli.domain.metadata import (
    anilist_status_label as _anilist_status_label,
    format_available_episodes,
    format_ep_progress as _format_ep_progress,
    format_info_metadata_line,
    format_next_airing,
    format_progress,
    format_time as formatTime,
    format_years,
    positive_int as _positive_int,
    set_next_airing_fields,
    should_refresh_anilist,
)
from allmanga_cli.playback.rules import (
    episode_transition_osd,
    marked_watched_osd,
    minimum_played_for_completion,
    pending_completion_osd,
    playback_is_actively_advancing,
    playback_looks_complete,
    playback_updates_history,
    prefetch_matches_request,
    should_clear_query_on_child_left,
    sync_queued_osd,
)
from allmanga_cli.playback.mpv_runtime import (
    TRANSITION_OSD_MS,
    cleanup_mpv_runtime,
    create_mpv_runtime,
)
from allmanga_cli.playback.mpv import MpvIpc
from allmanga_cli.playback import android as android_playback
from allmanga_cli.playback import desktop as desktop_playback
from allmanga_cli.playback import local as local_playback
from allmanga_cli.media.proxy_rules import (
    new_proxy_secret_path as _new_proxy_secret_path,
    proxy_filtered_headers as _proxy_filtered_headers,
    proxy_method_allowed as _proxy_method_allowed,
    proxy_path_authorized as _proxy_path_authorized,
    proxy_range_header as _proxy_range_header,
    proxy_response_headers as _proxy_response_headers,
)
from allmanga_cli.domain.sorting import (
    ANILIST_SORT_LABELS,
    ANILIST_SORT_MODES,
    anilist_history_timestamps,
    anilist_sort_label,
    next_anilist_sort_mode,
    normalize_anilist_sort_mode,
    previous_anilist_sort_mode,
    sort_anilist_shows,
)
from allmanga_cli.media.sources import (
    source_priority,
)
from allmanga_cli.core.terminal import (
    absolute_terminal_frame as _absolute_terminal_frame,
    bottom_align_panel_lines as _bottom_align_panel_lines,
    char_width as _char_width,
    display_width as _display_width,
    fit_terminal_line as _fit_terminal_line,
    picker_vertical_layout as _picker_vertical_layout,
    sanitize_terminal_text,
    split_display_prefix as _split_display_prefix,
    strip_ansi as _strip_ansi,
    truncate_display as _truncate_display,
)
from allmanga_cli.domain.titles import (
    extract_title_parts as _extract_title_parts,
    get_display_titles,
    get_show_display_title,
    wrap_title as _wrap_title,
)
from allmanga_cli.core.enrichment import (
    enrich_provider_results,
    _merge_anilist_into_provider as _merge_anilist_into_allanime
)
from allmanga_cli.domain.tracking import (
    apply_tracking_progress_local,
    completed_media_total,
    mark_tracking_progress_local,
    tracking_progress_for_sync,
    tracking_status_for_play,
    tracking_status_for_progress,
)
from allmanga_cli.media.urls import (
    validate_http_url,
    validate_optional_referer,
    validate_stream_url,
)
from allmanga_cli.core.processes import (
    MAX_YTDLP_JSON_BYTES,
    communicate_with_cleanup,
    read_bounded_process_stdout,
)
from allmanga_cli.state import secrets as secret_state
from allmanga_cli.state.paths import (
    ANILIST_QUEUE_PATH,
    CONFIG_PATH as CFG_PATH,
    HISTORY_PATH,
)
from allmanga_cli.state import anilist_queue as anilist_queue_state
from allmanga_cli.ui.fallback import fallback_pick as fallback_tui_pick
from allmanga_cli.ui.help import picker_help, search_input_help
from allmanga_cli.ui.covers import (
    MAX_COVER_BYTES,
    POSTER_HEIGHT,
    POSTER_WIDTH,
    chafa_cover_command as _chafa_cover_command,
    enforce_cache_limits as _enforce_cache_limits,
    fetch_cover_bytes,
    poster_symbol_lines as _poster_symbol_lines,
    poster_uses_native_protocol as _poster_uses_native_protocol,
)
from allmanga_cli.ui.poster import PosterManager
from allmanga_cli.ui.picker_render import (
    get_key as _get_key,
    loading_frame as _loading_frame,
    loading_line as _loading_line,
    match as _match,
    render_item as _render_item,
)
from allmanga_cli.ui import terminal_images
from allmanga_cli.ui.spinner import DEFAULT_SPINNER, spinner_from_config
from allmanga_cli.ui.anilist_menu import (
    LIST_STATUSES as ANILIST_LIST_STATUSES,
    loading_frame as anilist_menu_loading_frame,
    menu_header as anilist_menu_header,
    menu_navigation as anilist_menu_navigation,
)
from allmanga_cli.services.http import (
    ANILIST_TIMEOUT,
    anilist_urlopen,
    get_size,
    is_alive,
    request_json as _req,
)
from allmanga_cli.providers import ALLANIME, get_provider, provider_key, get_provider_registry, is_provider_active, _DEFAULT_PROVIDER_ID
from allmanga_cli.providers.shared.models import title_provider_id, title_provider_key
from allmanga_cli.providers import allanime as allanime_service
from allmanga_cli.services import anilist as anilist_service
from allmanga_cli.services import normalize as anilist_normalize
from allmanga_cli.context import FLAGS as runtime_flags
from allmanga_cli.core import reporting
from allmanga_cli.core import storage
from allmanga_cli.core import anilist
from allmanga_cli.core import streams
from allmanga_cli.ui import display, render_header_card, render_modal_card, render_search_header

# Persistence lives in core.storage; these aliases keep app_core callers and
# the many tests that reach for app_core.<fn> working unchanged.
is_incognito = storage.is_incognito
_cleanup_incognito_cache = storage.cleanup_incognito_cache
cover_cache_dir = storage.cover_cache_dir

atexit.register(_cleanup_incognito_cache)

# ── ANSI ──────────────────────────────────────────────────────────────────────
GREEN  = "\033[1;32m"; YELLOW = "\033[1;33m"; RED   = "\033[1;31m"
CYAN   = "\033[1;36m"; BOLD   = "\033[1m";    RESET = "\033[0m"

from allmanga_cli.ui.player_screen import _player_ui_state

def _add_status(m, color="\033[94m"):
    s = _player_ui_state
    if s["active"]:
        s["status_lines"].append(f"{color}{m}\033[0m")
        if len(s["status_lines"]) > 8:
            s["status_lines"].pop(0)

        try:
            from allmanga_cli.ui.player_screen import render
            render()
        except ImportError:
            pass
        return True
    return False

# Reporting lives in core.reporting; the player-screen status buffer is wired
# in as its sink so reporters route there while the player UI is active.
reporting.set_status_sink(_add_status)
info = reporting.info
ok = reporting.ok
warn = reporting.warn
err = reporting.err
debug_warn = reporting.debug_warn

stream_resolver.configure_reporters(info, ok, warn)
resolve_source = stream_resolver.resolve_source
local_proxy.configure_debug_reporter(debug_warn)
start_local_proxy = local_proxy.start_local_proxy
start_local_content_server = local_proxy.start_local_content_server
stop_local_proxy = local_proxy.stop_local_proxy
replace_active_local_proxy = local_proxy.replace_active_local_proxy
cleanup_active_local_proxy = local_proxy.cleanup_active_local_proxy
android_playback.configure_reporters(info, ok, warn, err)
PLAYERS = android_playback.PLAYERS
pkg_installed = android_playback.package_installed
play_android = android_playback.play_android

def set_ui_context(ui, show, ttype):
    ui.ui_show_ctx = show
    ui.ui_ttype_ctx = ttype

def get_ui_show(ui, default=None):
    if default is None:
        default = {}
    return ui.ui_show_ctx if ui.ui_show_ctx is not None else default

def get_ui_ttype(ui, default="sub"):
    return ui.ui_ttype_ctx if ui.ui_ttype_ctx is not None else default

def set_navigation_context(ui, search_prev=None, ep_prev=None, action_prev=None):
    if search_prev is not None:
        ui.search_prev_state = search_prev
    if ep_prev is not None:
        ui.ep_prev_state = ep_prev
    if action_prev is not None:
        ui.action_prev_state = action_prev

def get_search_prev(ui, default="SEARCH"):
    return ui.search_prev_state if ui.search_prev_state else default

def get_ep_prev(ui, default="SEARCH"):
    return ui.ep_prev_state if ui.ep_prev_state else default

def get_action_prev(ui, default="SEARCH"):
    return ui.action_prev_state if ui.action_prev_state else default

# ── TUI picker ────────────────────────────────────────────────────────────────
# Colors (Catppuccin-inspired, matching old fzf theme)
_C_NORMAL  = "\033[38;5;252m"           # #cccccc  normal item text
_C_SEL     = "\033[1;97m"               # bright white bold  selected item
_C_PTR     = "\033[38;2;243;139;168m"   # #f38ba8  pink pointer ❯
_C_PROMPT  = "\033[38;2;203;166;247m"   # #cba6f7  mauve prompt
_C_MATCH   = "\033[38;2;137;180;250m"   # #89b4fa  blue match highlight
_C_QUERY   = "\033[38;2;137;220;235m"   # #89dceb  teal query text
_C_HINT    = "\033[38;5;244m"           # #888888  dim hints / footer
_C_COUNT   = "\033[38;5;244m"           # same dim for count
_C_SCROLLI = "\033[38;2;243;139;168m"   # pink scroll indicators
_C_SECTION = "\033[1;38;5;183m"         # lavender section labels
_RST       = "\033[0m"


def buildEpStr(show, ttype):
    return format_progress(show) or format_available_episodes(show, ttype)

def buildYearStr(show):
    start_y = show.get("airedStart", {}).get("year") if show.get("airedStart") else None
    end_y = show.get("airedEnd", {}).get("year") if show.get("airedEnd") else None
    return format_years(start_y, end_y, show.get("status"))

def buildInfoMetadataLine(show, ttype, override_ep_str=None, local_only=False, hide_anilist_status=None):
    return format_info_metadata_line(
        show,
        ttype,
        override_ep_str=override_ep_str,
        local_only=local_only,
        hide_anilist_status=hide_anilist_status,
    )

should_update_anilist_progress = anilist.should_update_anilist_progress
sync_progress_and_checkpoint = anilist.sync_progress_and_checkpoint
sync_watched_to_anilist = anilist.sync_watched_to_anilist
save_and_sync_watched = anilist.save_and_sync_watched

ACTION_FEEDBACK_DURATION = 2.5

def set_action_feedback(show, msg):
    if isinstance(show, dict):
        show["_action_feedback"] = msg
        show["_action_feedback_time"] = time.time()

def get_active_feedback(show):
    if not isinstance(show, dict):
        return ""
    msg = str(show.get("_action_feedback") or "").strip()
    t = float(show.get("_action_feedback_time") or 0)
    if msg and (time.time() - t) < ACTION_FEEDBACK_DURATION:
        return msg
    return ""

def build_info_panel(
        show,
        ttype,
        w,
        parts,
        override_ep_str=None,
        main_title=None,
        local_only=False,
        hide_anilist_status=None):
    prepare_show_display_state(show, ttype, show.get("_sync_enabled") if "_sync_enabled" in show else None)
    card_lines = render_header_card(
        show,
        ttype=ttype,
        width=w,
        footer_text=None,
        override_ep_str=override_ep_str,
        main_title=main_title,
        local_only=local_only,
        hide_anilist_status=hide_anilist_status,
    )
    # The first 3 lines are Title, Alt Title, and Metadata
    parts.extend(card_lines[:3])


# ── Display (posters / spinner / alt-screen / loading) → ui.display ──────────────
# All terminal-presentation logic lives in ui.display; these aliases keep the
# many app_core.<name> callers (app/, ui/, cli/, tests) working unchanged.
# hovered-show id is app_core/orchestrator state the app layer writes; display
# reads it through the injected hook below.
_hovered_show_id = None  # provider id of the show hovered in the picker (app layer writes it)
display.configure(hovered_show_id_fn=lambda: globals().get("_hovered_show_id"))

_request_poster_redraw = display._request_poster_redraw
_configured_loading_frame = display._configured_loading_frame
_configure_spinner_from_config = display._configure_spinner_from_config
_poster_manager = display._poster_manager
_clear_poster_downloads = display._clear_poster_downloads
clear_terminal_images = display.clear_terminal_images
_poster_footer_line = display._poster_footer_line
_poster_needs_tick = display._poster_needs_tick
_get_poster = display._get_poster
enter_alt_screen = display.enter_alt_screen
exit_alt_screen = display.exit_alt_screen
restore_terminal = display.restore_terminal
with_loading = display.with_loading
render_anilist_menu_loading = display.render_anilist_menu_loading
with_anilist_menu_loading = display.with_anilist_menu_loading
with_footer_loading = display.with_footer_loading

def load_anilist_browse(token, status):
    return with_anilist_menu_loading(
        status,
        f"Loading AniList list: {status}",
        fetch_anilist_list,
        token,
        status,
    )


def enrich_show_if_missing(show: dict) -> None:
    if not show:
        return
    if show.get("aniListId") or show.get("_anilist_score"):
        return
    
    show_id = title_provider_id(show)
    if not show_id:
        return
        
    provider = _provider_for_title(show)
    if provider.id not in ("anidbapp", "animexin", "lucifer", "animekhor", "animegg", "anizone"):
        return
        
    get_title_fn = getattr(provider, "get_title", None)
    if not get_title_fn:
        return

    try:
        title_data = get_title_fn(show_id)
        if title_data:
            # Merge any newly scraped data (description, episodes, etc.) into the active show object
            for k, v in title_data.items():
                if k in ("status", "episodeCount", "_next_airing_ep", "_next_airing_at", "_next_airing_time", "aniListId", "malId", "format") and v:
                    show[k] = v
                elif v and not show.get(k):
                    show[k] = v
                elif k == "availableEpisodes" and isinstance(v, dict):
                    show.setdefault(k, {})
                    for ep_k, ep_v in v.items():
                        if ep_v > show[k].get(ep_k, 0):
                            show[k][ep_k] = ep_v

            if title_data.get("aniListId") or title_data.get("malId"):
                from allmanga_cli.core.anilist import fetch_anilist_by_ids
                from allmanga_cli.core.enrichment import _merge_anilist_into_provider
                from allmanga_cli.core.storage import load_config, get_title_sync
                
                # Check if sync is disabled globally or via flags
                sync_allowed = True
                if runtime_flags.sync_force_off:
                    sync_allowed = False
                elif not runtime_flags.sync_force_on:
                    sync_allowed = get_title_sync(show)
                    
                token = load_config().get("anilist_token") if sync_allowed else None
                al_ids = [title_data["aniListId"]] if title_data.get("aniListId") else None
                mal_ids = [title_data["malId"]] if title_data.get("malId") else None
                al_data = fetch_anilist_by_ids(token, anilist_ids=al_ids, mal_ids=mal_ids)
                if al_data:
                    _merge_anilist_into_provider(show, al_data[0])
    except Exception as e:
        debug_warn("Late enrichment failed", e)


def make_info_fn(shows_getter, ui):
    """Return an ``info_fn`` callback suitable for passing to ``tui_pick``.

    *shows_getter* is a zero-argument callable that returns the current list
    of show dicts (same list whose indices ``tui_pick`` returns).
    *ui* is the current :class:`~allmanga_cli.context.UiState`.

    When the user presses ``Ctrl+O`` on a highlighted item, the info screen
    is shown for that show and control returns to the picker automatically.
    """
    def _info_fn(idx: int) -> None:
        from allmanga_cli.ui.info_screen import show_info_screen
        shows = shows_getter()
        if not shows or not (0 <= idx < len(shows)):
            return
        with_loading("Loading title info…", enrich_show_if_missing, shows[idx])
        show_info_screen(
            shows[idx],
            poster_manager=_poster_manager,
            ui=ui,
        )

    return _info_fn


def make_single_show_info_fn(show, ui):
    """Return an ``info_fn`` for pickers bound to a single show (e.g. details, episodes)."""
    def _info_fn(idx: int) -> None:
        if not show:
            return
        with_loading("Loading title info…", enrich_show_if_missing, show)
        from allmanga_cli.ui.info_screen import show_info_screen
        show_info_screen(
            show,
            poster_manager=_poster_manager,
            ui=ui,
        )
    return _info_fn


def _exit_player_screen(close_alt=False):
    try:
        from allmanga_cli.ui.player_screen import stop_loading_ticker
        stop_loading_ticker()
    except Exception:
        pass
    if close_alt:
        exit_alt_screen()
    _player_ui_state["active"] = False

def _get_player_poster(show):
    if not show:
        return ""
    globals()["_hovered_show_id"] = show.get("_id") or show.get("id")
    return _get_poster(show) or ""

def _playback_episode_summary(show, player_state, ttype="sub"):
    if not isinstance(show, dict):
        return ""
        
    fmt = str(show.get("format") or show.get("type") or "").upper()
    total = _positive_int(show.get("episodeCount"))
    if fmt == "MOVIE" or total == 1:
        return ""
        
    available = None
    try:
        available = int((show.get("availableEpisodes") or {}).get(ttype))
    except (TypeError, ValueError):
        available = None
    if available is None:
        next_ep = _positive_int(show.get("_next_airing_ep"))
        if next_ep:
            available = max(0, next_ep - 1)
    if available is None:
        available = _positive_int(player_state.get("total_eps"))

    if available is not None:
        return f"Episodes {available}/{total if total else '?'}"
    if total:
        return f"Total {total}"
    return ""





# ── Persistence (core.storage) ────────────────────────────────────────────────
# Definitions live in core/storage.py; aliases keep existing callers working.
_atomic_write_json = storage._atomic_write_json
write_private_log = storage.write_private_log
write_exception_log = storage.write_exception_log
load_prefs = storage.load_prefs
save_prefs = storage.save_prefs
get_preferred_mirror = storage.get_preferred_mirror
toggle_preferred_mirror = storage.toggle_preferred_mirror
get_episode_order = storage.get_episode_order
toggle_episode_order = storage.toggle_episode_order
get_title_sync_preference = storage.get_title_sync_preference
get_title_sync = storage.get_title_sync
set_title_sync = storage.set_title_sync
get_local_progress = storage.get_local_progress
get_local_episode_label = storage.get_local_episode_label
get_history_entry = storage.get_history_entry
get_last_synced_progress = storage.get_last_synced_progress
episode_id_for_progress = storage.episode_id_for_progress
ANILIST_HISTORY_STRIP_KEYS = storage.ANILIST_HISTORY_STRIP_KEYS
HISTORY_SHOW_STRIP_KEYS = storage.HISTORY_SHOW_STRIP_KEYS
sanitize_show_for_history = storage.sanitize_show_for_history
sanitize_history_list = storage.sanitize_history_list
write_history_progress = storage.write_history_progress
set_last_synced_progress = storage.set_last_synced_progress

def prepare_show_display_state(show, ttype="sub", sync_enabled=None):
    if not show:
        return show
    if is_incognito():
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
    if not show.get("_progress_authority"):
        show["_progress_authority"] = "AL" if sync_enabled else "LOCAL"
    return show

get_resume_time = storage.get_resume_time
save_resume_time = storage.save_resume_time
get_pending_completion = storage.get_pending_completion
save_pending_completion = storage.save_pending_completion
clear_pending_completion = storage.clear_pending_completion
get_al_match = storage.get_al_match
save_al_match = storage.save_al_match
get_source_anilist_match = storage.get_source_anilist_match
save_source_anilist_match = storage.save_source_anilist_match

def playback_ep_from_history_entry(h, ttype=None):
    show = h.get("show", {})
    tt = ttype or h.get("translation_type", "sub")
    episode_ids = ensure_episode_ids(show, tt)
    return history_domain.playback_episode(
        h,
        translation_type=tt,
        episode_ids=episode_ids,
        resume_time=get_resume_time,
    )

_preserve_invalid_state_file = storage._preserve_invalid_state_file
load_history = storage.load_history
save_history = storage.save_history
delete_history_entry = storage.delete_history_entry

fetch_anilist_media = anilist.fetch_anilist_media
get_show_anilist_id = anilist.get_show_anilist_id
get_show_mal_id = anilist.get_show_mal_id
get_anilist_media_id = anilist.get_anilist_media_id
update_anime_from_anilist_media = anilist.update_anime_from_anilist_media

refresh_history_entry_from_anilist = anilist.refresh_history_entry_from_anilist

def apply_allanime_metadata_to_history_show(show, allanime_show):
    changed = False

    for key in ("status", "episodeCount", "airedStart", "score", "type", "season"):
        val = allanime_show.get(key)
        if val is not None and str(show.get(key)) != str(val):
            show[key] = val
            changed = True

    for key in ("thumbnail", "name", "englishName", "nativeName"):
        val = allanime_show.get(key)
        if val and not show.get(key):
            show[key] = val
            changed = True

    avail = allanime_show.get("availableEpisodes")
    if avail and isinstance(avail, dict):
        current_avail = show.get("availableEpisodes") or {}
        if current_avail != avail:
            show["availableEpisodes"] = dict(avail)
            changed = True

    return changed


refresh_history_anilist_airing_batch = anilist.refresh_history_anilist_airing_batch

def refresh_history_entry_allanime_catalog(entry):
    import time
    show = (entry or {}).get("show", {})
    ttype = entry.get("translation_type", "sub")
    show_id = show.get("_id")

    changed = False
    if not show_id:
        return False

    pkey = title_provider_key(show)
    if pkey == "allanime":
        try:
            allanime_show = get_allanime_show(show_id)
            if allanime_show:
                if apply_allanime_metadata_to_history_show(show, allanime_show):
                    changed = True
        except Exception as e:
            debug_warn("Failed to fetch show metadata during AllAnime refresh", e)

        try:
            catalog = fetch_episode_catalog(show_id, ttype)
            if catalog.get("state") == "loaded":
                old_avail = (show.get("availableEpisodes") or {}).get(ttype)
                new_avail = len(catalog.get("ids", []))

                current_ids = show.get("_episode_ids") or []
                if old_avail != new_avail or show.get("_episode_ids_ttype") != ttype or current_ids != catalog["ids"]:
                    if not show.get("availableEpisodes"):
                        show["availableEpisodes"] = {}
                    update_available_count_from_episode_ids(show, ttype, catalog["ids"], catalog.get("detail"))
                    changed = True

                if show.get("_episode_catalog_state") != "loaded":
                    show["_episode_catalog_state"] = "loaded"
                    changed = True

                # Since catalog load succeeded, mark it checked
                new_checked = int(time.time())
                if show.get("_allanime_checked_at") != new_checked:
                    show["_allanime_checked_at"] = new_checked
                    changed = True
        except Exception as e:
            debug_warn("Failed to fetch episode catalog during AllAnime refresh", e)
    else:
        try:
            prov = _provider_for_title(show)
            catalog = prov.episode_catalog(show_id, ttype=ttype)
            if catalog and catalog.get("state") == "loaded":
                old_avail = (show.get("availableEpisodes") or {}).get(ttype)
                new_avail = len(catalog.get("ids", []))
                current_ids = show.get("_episode_ids") or []
                if old_avail != new_avail or show.get("_episode_ids_ttype") != ttype or current_ids != catalog.get("ids", []):
                    if not show.get("availableEpisodes"):
                        show["availableEpisodes"] = {}
                    show["availableEpisodes"][ttype] = new_avail
                    show["_episode_ids"] = catalog.get("ids", [])
                    show["_episode_labels"] = catalog.get("labels", {})
                    show["_episode_ids_ttype"] = ttype
                    changed = True
                if show.get("_episode_catalog_state") != "loaded":
                    show["_episode_catalog_state"] = "loaded"
                    changed = True
                if "aniListId" not in show and catalog.get("aniListId"):
                    show["aniListId"] = str(catalog["aniListId"])
                    changed = True
        except Exception as e:
            debug_warn(f"Failed to refresh episode catalog for {pkey}", e)

    return changed

save_refreshed_history = storage.save_refreshed_history
patch_history_entry_show = storage.patch_history_entry_show
load_search_history = storage.load_search_history
save_search_history = storage.save_search_history
delete_search_history_entry = storage.delete_search_history_entry
clear_search_history = storage.clear_search_history
format_history_entry = storage.format_history_entry
format_history_updated_time = storage.format_history_updated_time
history_entry_progress = storage.history_entry_progress
history_entry_category = storage.history_entry_category
filter_history_entries = storage.filter_history_entries

load_config = storage.load_config
save_config = storage.save_config

def allanime_frontend_domain(cfg=None):
    return ALLANIME.browser_url("", cfg=cfg)


def allanime_episode_url(show_id, episode, ttype="sub", cfg=None):
    show_id = str(show_id or "").strip()
    episode = str(episode or "").strip()
    if not show_id or not episode:
        return ""
    return ALLANIME.browser_url(show_id, episode, ttype, cfg)


def open_external_url(url):
    try:
        url = validate_http_url(url)
    except ValueError:
        return False
    if is_termux():
        opener = shutil.which("termux-open-url") or shutil.which("termux-open")
        command = (
            [opener, url]
            if opener else
            ["am", "start", "-a", "android.intent.action.VIEW", "-d", url]
        )
    elif sys.platform == "darwin":
        command = ["open", url]
    elif os.name == "nt":
        command = ["cmd", "/c", "start", "", url]
    else:
        opener = shutil.which("xdg-open")
        command = [opener, url] if opener else []
    if not command:
        return False
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False


sanitize_token = storage.sanitize_token

save_anilist_token = anilist.save_anilist_token
clear_anilist_token = anilist.clear_anilist_token
anilist_token_storage_status = anilist.anilist_token_storage_status
mask_token = anilist.mask_token
anilist_auth_status_lines = anilist.anilist_auth_status_lines
stored_anilist_token = anilist.stored_anilist_token
anilist_auth_login_existing_lines = anilist.anilist_auth_login_existing_lines
anilist_auth_token_lines = anilist.anilist_auth_token_lines
prompt_anilist_token = anilist.prompt_anilist_token

def redact_sensitive_text(content):
    text = str(content)
    text = re.sub(
        r"(?i)(Authorization\s*:\s*Bearer\s+)[^\s'\"]+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(
        r"(https?://[^\s'\"<>?]+)\?[^\s'\"<>]+",
        r"\1?<redacted>",
        text,
    )
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        "<redacted-jwt>",
        text,
    )
    return text

# Wire storage's injected upper-layer hooks: private-log redaction, provider
# episode catalogs, and display-state priming (defined later in this module).
storage.configure_redactor(redact_sensitive_text)
storage.configure(
    episode_ids_fn=lambda show, ttype: ensure_episode_ids(show, ttype),
    prepare_display_state_fn=lambda show, ttype="sub", sync_enabled=None: (
        prepare_show_display_state(show, ttype, sync_enabled)
    ),
)
anilist.configure(
    action_feedback_fn=lambda show, msg: set_action_feedback(show, msg),
    allanime_catalog_refresh_fn=lambda entry: refresh_history_entry_allanime_catalog(entry),
)
streams.configure(
    episode_data_fn=lambda show_id, ep, ttype="sub", provider_id=None: (
        get_episode_data(show_id, ep, ttype, provider_id=provider_id)
    ),
)

# ── AniList Tracking ──────────────────────────────────────────────────────────
scrobble_anilist = anilist.scrobble_anilist
_fuzzy_date_has_value = anilist._fuzzy_date_has_value
_today_fuzzy_date = anilist._today_fuzzy_date
_anilist_date_updates = anilist._anilist_date_updates
update_anilist_entry = anilist.update_anilist_entry

# Durable AniList write-queue + reconciliation live in core.anilist.
_load_anilist_queue = anilist._load_anilist_queue
_save_anilist_queue = anilist._save_anilist_queue
_anilist_mutation_key = anilist._anilist_mutation_key
_enqueue_anilist_progress = anilist._enqueue_anilist_progress
_update_queued_mutation = anilist._update_queued_mutation
_remove_queued_mutation = anilist._remove_queued_mutation
_checkpoint_queued_progress = anilist._checkpoint_queued_progress
_finish_queued_pending_completion = anilist._finish_queued_pending_completion
_run_queued_anilist_progress = anilist._run_queued_anilist_progress
_start_queued_anilist_progress = anilist._start_queued_anilist_progress
queue_anilist_progress = anilist.queue_anilist_progress
retry_queued_anilist_writes = anilist.retry_queued_anilist_writes
flush_anilist_writes = anilist.flush_anilist_writes
_reconcile_status = anilist._reconcile_status
_push_local_progress = anilist._push_local_progress

fetch_anilist_list = anilist.fetch_anilist_list
search_anilist = anilist.search_anilist
fetch_anilist_by_ids = anilist.fetch_anilist_by_ids
# Shared read caches now live in core.anilist; keep aliases for callers/tests.
_anilist_list_cache = anilist._anilist_list_cache
_anilist_search_cache = anilist._anilist_search_cache

_provider_search_cache = {}

def provider_display_name(provider_id=None):
    return get_provider(provider_id).name


def make_provider_oneshot_search(query, ttype, provider_id=None):
    loading = True
    results = []
    error = ""
    cfg = load_config()
    spinner_style = spinner_from_config(cfg)
    token = cfg.get("anilist_token")
    
    from allmanga_cli.context import FLAGS as runtime_flags
    use_sync = runtime_flags.sync_force_on or (cfg.get("sync") and not runtime_flags.sync_force_off)
    if not use_sync:
        token = ""

    provider_id = provider_key(provider_id)
    provider_name = provider_display_name(provider_id)
    cache_key = (query, ttype, provider_id)

    if cache_key in _provider_search_cache:
        loading = False
        results = _provider_search_cache[cache_key]
        
        def get_results(): return results
        def get_loading(): return ""
        def get_error(): return ""
        def live_fn(q=""):
            opts = [f"{s.get('name')}" for s in results]
            return opts, "", True
            
        return live_fn, get_results, get_loading, get_error

    def _fetch():
        nonlocal loading, results, error
        try:
            shows = None
            al_shows = None

            def _fetch_aa():
                nonlocal shows, error
                try:
                    shows = search_anime(
                        query,
                        ttype,
                        raise_errors=True,
                        provider_id=provider_id,
                    )
                except SearchFailure as exc:
                    error = str(exc)
                    shows = []
            def _fetch_al(): nonlocal al_shows; al_shows = search_anilist(token, query)

            threads = [threading.Thread(target=_fetch_aa)]
            if token: threads.append(threading.Thread(target=_fetch_al))

            for t in threads: t.start()
            for t in threads: t.join()

            if shows:
                # Pass the results to the central metadata enrichment builder
                shows = enrich_provider_results(shows, token, al_shows)

            if shows:
                for s in shows:
                    if s.get("status") == "NOT_YET_RELEASED":
                        continue
                    results.append(s)
                _provider_search_cache[cache_key] = list(results)

        except Exception as e:
            if not error:
                error = search_failure_message(provider_name, e)
            try:
                write_exception_log("bg_crash.log")
            except Exception as log_error:
                debug_warn("Failed to write background crash log", log_error)
        finally:
            loading = False

    threading.Thread(target=_fetch, daemon=True).start()

    def get_results():
        return results

    def get_loading():
        if loading:
            try: w = os.get_terminal_size().columns
            except OSError: w = 80

            msg = "Searching..."
            return _loading_line(msg, w, spinner_style)
        return ""

    def get_error():
        return error

    def live_fn(q=""):
        opts = [f"{s.get('name')}" for s in results]
        return opts, get_loading(), not loading

    return live_fn, get_results, get_loading, get_error


def make_allanime_oneshot_search(query, ttype, provider_id=None):
    return make_provider_oneshot_search(query, ttype, provider_id)

def make_anilist_oneshot_search(token, initial_query):
    results = []
    loading = True
    error = ""
    spinner_style = display._spinner_style

    def worker():
        nonlocal results, loading, error
        try:
            res = search_anilist(token, initial_query, raise_errors=True)
            if res:
                results = res
        except SearchFailure as exc:
            error = str(exc)
        finally:
            loading = False

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def get_loading():
        if loading:
            try: w = os.get_terminal_size().columns
            except OSError: w = 80

            return _loading_line("Searching...", w, spinner_style)
        return ""

    def live_fn(q):
        opts = [f"{s['name']}" for s in results]
        return opts, get_loading(), not loading

    return live_fn, lambda: list(results), get_loading, lambda: error

def _search_input_header(source_name, esc_action="quit"):
    def _hdr(si):
        C_K = "\033[38;5;244m"
        R = "\033[0m"
        parts = [""]
        parts.append(f"{C_K}Use Up/Down to browse previous searches.{R}")
        parts.append(f"\033[38;5;250mProvider: \033[1;97m{source_name}{R}")
        if globals().get("_search_error"):
            parts.append(f"{C_K}{globals()['_search_error']}  │  Esc={esc_action}{R}")
        else:
            parts.append(f"{C_K}Enter=search  ? = Help  Esc={esc_action}{R}")
        return "\n".join(parts)
    return _hdr

def _search_cover_header(get_results):
    def _hdr(si):
        shows = get_results()
        if shows and 0 <= si < len(shows):
            globals()["_hovered_show_id"] = shows[si].get("_id") or shows[si].get("id")
            poster = _get_poster(shows[si])
            if poster:
                return poster
        return ""
    return _hdr

def _search_result_header(source_name, query_str, ttype, get_results, get_loading, esc_action="quit", get_error_fn=None):
    def _hdr(si):
        C_K = "\033[38;5;244m"
        R = "\033[0m"
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        parts = []
        safe_query = sanitize_terminal_text(query_str)
        filter_query = sanitize_terminal_text(
            globals().get("_active_picker_query", "")
        )
        shows = get_results()
        loading_msg = get_loading()

        if loading_msg:
            selected_show = {}
            parts.append("")
            parts.append(f"{C_K}Use Up/Down to browse previous searches.{R}")
            parts.append(f"\033[38;5;250mSource: \033[1;97m{source_name}\033[0m")
        elif shows and 0 <= si < len(shows):
            selected_show = shows[si]
            build_info_panel(selected_show, ttype, w, parts)
        else:
            selected_show = {}
            parts.append("")
            if shows and filter_query:
                parts.append(
                    f"{C_K}No match: "
                    f"{_truncate_display(filter_query, max(1, w - 11))}{R}"
                )
            else:
                parts.append("")
            parts.append(
                f"\033[38;5;250mSource: "
                f"\033[1;97m{source_name}\033[0m"
            )

        if loading_msg:
            parts.append(loading_msg)
        elif shows:
            parts.append(_poster_footer_line(selected_show, f'{len(shows)} result(s) for "{safe_query}"  │  Enter=select  ? = Help  Left=search  Esc={esc_action}', w))
        else:
            err_msg = get_error_fn() if get_error_fn else ""
            if err_msg:
                parts.append(f"\033[38;5;196m{err_msg}{R}  │  Left=new search  Esc={esc_action}")
            else:
                parts.append(f"{C_K}No results for \"{safe_query}\"  │  Left=new search  Esc={esc_action}{R}")
        return "\n".join(parts)
    return _hdr

def _cached_search_results(query_str, query_key, shows_key, make_search):
    if query_str == globals().get(query_key) and globals().get(shows_key):
        shows = globals()[shows_key]
        return None, lambda: shows, lambda: "", lambda: ""
    return make_search()

def _remember_search_results(query_str, shows, query_key, shows_key):
    if shows:
        globals()[query_key] = query_str
        globals()[shows_key] = shows

def _manual_match_input_header(show, p_name="Provider", error=""):
    def _hdr(si):
        C_K = "\033[38;5;244m"
        C_T = "\033[1;97m"
        R = "\033[0m"
        anilist_title = show.get("name") or show.get("englishName") or "" if isinstance(show, dict) else str(show or "")
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        parts = [
            "",
            f"{C_K}Search {p_name} and choose the correct stream title.{R}",
            f"{C_T}{_truncate_display(anilist_title, w)}{R}",
        ]
        footer_text = f"{error} • Esc=cancel" if error else "Enter=search • Esc=cancel"
        parts.append(_poster_footer_line(show, footer_text, w))
        return "\n".join(parts)
    return _hdr

def _manual_anilist_input_header(show, error=""):
    def _hdr(si):
        C_K = "\033[38;5;244m"
        C_T = "\033[1;97m"
        R = "\033[0m"
        source_title = show.get("_allanime_name") or show.get("name") or "" if isinstance(show, dict) else str(show or "")
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        parts = [
            "",
            f"{C_K}Search AniList and select tracking title.{R}",
            f"{C_T}{_truncate_display(source_title, w)}{R}",
        ]
        footer_text = f"\033[38;5;222m{error}\033[0m • Enter=search • Esc=cancel" if error else "Enter=search • Esc=cancel"
        parts.append(_poster_footer_line(show, footer_text, w))
        return "\n".join(parts)
    return _hdr

def _select_provider_for_match(flags, ui, current_pid, anilist_show, ttype="sub"):
    from allmanga_cli.providers import available_providers
    provs = available_providers()
    if not provs:
        return current_pid

    current_key = provider_key(current_pid)
    ordered_keys = [current_key] if current_key in provs else []
    for k in sorted(provs.keys()):
        if k not in ordered_keys:
            ordered_keys.append(k)

    opts = [provider_display_name(k) for k in ordered_keys]

    def _hdr(idx):
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80

        C_W = "\033[1;37m"
        C_S = "\033[38;5;250m"
        C_K = "\033[38;5;244m"
        C_Y = "\033[38;5;222m"
        C_C = "\033[36m"
        R = "\033[0m"

        # Line 1: Primary Title (Romaji)
        t_romaji = _truncate_display(anilist_show.get("name") or anilist_show.get("englishName") or "Unknown Title", w)
        line1 = f"{C_W}{t_romaji}{R}"

        # Line 2: English Title or AL metadata fallback
        t_eng = anilist_show.get("englishName")
        if t_eng and t_eng.strip().lower() != (anilist_show.get("name") or "").strip().lower():
            line2 = f"{C_S}{_truncate_display(t_eng, w)}{R}"
        else:
            al_list = str(anilist_show.get("_anilist_list") or "").upper() or "WATCHING"
            al_prog = anilist_show.get("_anilist_progress", 0)
            line2 = f"{C_K}AL {al_list} \u2022 EP {al_prog} \u2022 {ttype.upper()}{R}"

        # Line 3: Current Provider vs Target (Hovered) Provider with Type/Language tags
        curr_name = provider_display_name(current_key)
        hov_key = ordered_keys[idx] if (0 <= idx < len(ordered_keys)) else current_key
        hov_name = provider_display_name(hov_key)
        hov_info = get_provider_registry().get(hov_key, {})
        ptype = str(hov_info.get("type") or "anime").title()
        langs = "/".join(l.upper() for l in hov_info.get("languages", ["sub"]))
        badge = f" [{ptype} \u2022 {langs}]" if ptype else ""
        line3 = f"{C_Y}Current: {curr_name}{R}  {C_K}\u2502{R}  {C_C}Target: {hov_name}{badge}{R}"

        # Line 4: Action Hints
        line4 = f"{C_K}Enter=select  Left/Esc=cancel{R}"

        return f"{line1}\n{line2}\n{line3}\n{line4}"

    idx = tui_pick(
        flags, ui, "Select Provider",
        opts,
        header_fn=_hdr,
        help_dict={"Enter": "Select provider", "Esc": "Cancel"}
    )
    if idx is None or idx < 0 or idx >= len(ordered_keys):
        return None
    return ordered_keys[idx]


def _confirm_auto_match(flags, ui, current_pid, target_pid, anilist_show, matched_show, ttype="sub"):
    opts = [
        f'Link "{matched_show.get("name") or matched_show.get("englishName") or "Matched Title"}"',
        "Search Manually",
        "Back to Providers",
    ]
    target_title = matched_show.get("name") or matched_show.get("englishName") or "Unknown Stream Title"
    al_title = anilist_show.get("name") or anilist_show.get("englishName") or ""
    al_eng = anilist_show.get("englishName")

    def _hdr(idx):
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80

        if al_eng and al_eng.strip().lower() != (target_title or "").strip().lower():
            secondary = al_eng
        else:
            secondary = f"AniList: {al_title}" if al_title and al_title.lower() != target_title.lower() else ""

        curr_name = provider_display_name(current_pid)
        t_name = provider_display_name(target_pid)
        trans_line = f"\033[38;5;222m{curr_name}\033[0m  \033[38;5;244m➔\033[0m  \033[36m{t_name}\033[0m"

        t_info = get_provider_registry().get(target_pid, {})
        langs = "/".join(l.upper() for l in t_info.get("languages", ["sub", "dub"]))
        avail_eps = matched_show.get("availableEpisodes", {}).get(ttype) or 0
        eps_badge = f"Avail {avail_eps} EPs • " if avail_eps else ""
        source = matched_show.get("_match_source")
        match_tag = "✓ Matched by ID" if source == "id" else ("✓ Saved link" if source in ("stored", "manual") else "✓ Suggested match")
        status_line = f"\033[38;5;250m{match_tag} • {eps_badge}{langs}\033[0m"

        return render_modal_card(target_title, secondary, trans_line, status_line, width=w)

    hints = {"Link Title": target_title}
    idx = tui_pick(
        flags, ui, "Confirm Match",
        opts,
        header_fn=_hdr,
        hints=hints,
        help_dict={"Enter": "Select", "Esc": "Cancel"}
    )
    if idx is None or idx in (-2, -3) or idx == 2:
        return "back"
    elif idx == 1:
        return "search"
    elif idx == 0:
        return "link"
    return "back"


def _no_match_prompt(flags, ui, current_pid, target_pid, anilist_show, ttype="sub"):
    opts = [
        "Search Manually",
        "Back to Providers",
    ]

    def _hdr(idx):
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80

        t_romaji = anilist_show.get("name") or anilist_show.get("englishName") or "Unknown Title"
        t_eng = anilist_show.get("englishName")
        if t_eng and t_eng.strip().lower() != (anilist_show.get("name") or "").strip().lower():
            secondary = t_eng
        else:
            al_list = str(anilist_show.get("_anilist_list") or "").upper() or "WATCHING"
            al_prog = anilist_show.get("_anilist_progress", 0)
            secondary = f"\033[38;5;244mAL {al_list} • EP {al_prog} • {ttype.upper()}\033[0m"

        curr_name = provider_display_name(current_pid)
        t_name = provider_display_name(target_pid)
        trans_line = f"\033[38;5;222m{curr_name}\033[0m  \033[38;5;244m➔\033[0m  \033[36m{t_name}\033[0m"
        status_line = "\033[38;5;222m* No match found\033[0m"

        return render_modal_card(t_romaji, secondary, trans_line, status_line, width=w)

    idx = tui_pick(
        flags, ui, "Select Option",
        opts,
        header_fn=_hdr,
        help_dict={"Enter": "Select", "Esc": "Back"}
    )
    if idx is None or idx in (-2, -3) or idx == 1:
        return "back"
    elif idx == 0:
        return "search"
    return "back"


def _run_manual_match_search(flags, ui, anilist_show, ttype, provider_id=None, allow_provider_change=False):
    al_title = anilist_show.get("name") or anilist_show.get("englishName") or ""
    al_id = str(anilist_show.get("_id") or anilist_show.get("id") or "")
    current_pid = provider_key(provider_id or anilist_show.get("_provider") or getattr(ui, "ui_provider_ctx", None))
    target_pid = current_pid

    while True:
        if allow_provider_change:
            chosen_pid = _select_provider_for_match(flags, ui, target_pid, anilist_show, ttype)
            if not chosen_pid:
                return None
            target_pid = chosen_pid
            p_name = provider_display_name(target_pid)

            # Auto-match on selected provider
            matched = with_loading(
                f"Matching title on {p_name}...",
                match_anilist_show_to_provider,
                anilist_show,
                ttype,
                provider_id=target_pid,
            )
            if matched:
                choice = _confirm_auto_match(flags, ui, current_pid, target_pid, anilist_show, matched, ttype)
                if choice == "link":
                    matched["_match_source"] = matched.get("_match_source") or "auto"
                    if al_id:
                        save_al_match(al_id, matched)
                    return _merge_anilist_into_allanime(matched, anilist_show)
                elif choice == "back":
                    continue
            else:
                choice = _no_match_prompt(flags, ui, current_pid, target_pid, anilist_show, ttype)
                if choice == "back":
                    continue

        p_name = provider_display_name(target_pid)
        query = extract_franchise_query(al_title) or al_title
        search_error = ""

        while True:
            query = tui_pick(
                flags, ui, f"Match {p_name}",
                [],
                header_fn=_manual_match_input_header(anilist_show, p_name=p_name, error=search_error),
                return_query_on_enter=True,
                initial_query=query,
                is_search=True,
                help_dict=search_input_help()
            )
            if query == -2 or not query:
                if allow_provider_change:
                    break  # Break out to provider selection loop
                return None
            query = str(query).strip()
            if not query:
                continue
            search_error = ""

            live_fn, get_results, get_loading, get_error = make_provider_oneshot_search(query, ttype, target_pid)
            initial_opts = [s.get("name", "Unknown") for s in get_results()]
            idx = tui_pick(
                flags, ui, f"Match {p_name}",
                initial_opts,
                header_fn=_search_result_header(p_name, query, ttype, get_results, get_loading, get_error_fn=get_error),
                top_header_fn=_search_cover_header(get_results),
                live_fn=live_fn,
                help_dict=picker_help("Link title", "Search again", "Cancel")
            )
            if idx == -2:
                if allow_provider_change:
                    break
                return None
            if idx == -3:
                continue
            if idx == -4:
                search_error = get_error() or f'No results found for "{query}"'
                continue
            if idx >= 0:
                shows = get_results()
                if idx >= len(shows):
                    continue
                chosen = shows[idx]
                chosen["_match_source"] = "manual"
                if al_id:
                    save_al_match(al_id, chosen)
                return _merge_anilist_into_allanime(chosen, anilist_show)

def _confirm_auto_anilist_match(flags, ui, provider_show, anilist_show):
    al_romaji = anilist_show.get("name") or anilist_show.get("englishName") or "Unknown Title"
    al_eng = anilist_show.get("englishName")
    al_id = str(anilist_show.get("_id") or anilist_show.get("id") or "")
    p_title = provider_show.get("name") or ""
    p_name = (provider_show.get("_provider_name") or (provider_show.get("_provider") or "").title()) or "Provider"

    opts = [
        "Link Title",
        "Search Manually",
        "Back",
    ]

    def _hdr(idx):
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80

        if al_eng and al_eng.strip().lower() != al_romaji.strip().lower():
            secondary = al_eng
        elif p_title and p_title.lower() != al_romaji.lower():
            secondary = f"Source: {p_title}"
        else:
            secondary = ""

        id_badge = f" (ID: {al_id})" if al_id else ""
        trans_line = f"\033[38;5;222m{p_name}\033[0m  \033[38;5;244m➔\033[0m  \033[36mAniList{id_badge}\033[0m"

        al_status = str(anilist_show.get("status") or "").title() or "Finished"
        al_fmt = str(anilist_show.get("format") or anilist_show.get("type") or "TV").upper()
        al_eps = anilist_show.get("episodeCount")
        eps_str = f" • EP {al_eps}" if al_eps else ""
        al_score = anilist_show.get("score") or anilist_show.get("averageScore")
        score_str = f" • ★ {al_score}" if al_score else ""
        source = anilist_show.get("_match_source")
        tag = "✓ Matched by ID" if source == "id" else "✓ Suggested match"
        status_line = f"\033[38;5;250m{tag} • {al_status} • {al_fmt}{eps_str}{score_str}\033[0m"

        return render_modal_card(al_romaji, secondary, trans_line, status_line, width=w)

    hints = {"Link Title": al_romaji}
    idx = tui_pick(
        flags, ui, "Confirm Match",
        opts,
        header_fn=_hdr,
        hints=hints,
        help_dict={"Enter": "Select", "Esc": "Cancel"}
    )
    if idx is None or idx in (-2, -3) or idx == 2:
        return "back"
    elif idx == 1:
        return "search"
    elif idx == 0:
        return "link"
    return "back"


def _find_fuzzy_anilist_candidate(allanime_show, token):
    # Step 1: Exact provider aniListId
    provider_al_id = str(allanime_show.get("aniListId") or "")
    if provider_al_id:
        try:
            media = fetch_anilist_media(token, provider_al_id)
            if media:
                norm = anilist_normalize.normalize_media(media)
                norm["_match_source"] = "id"
                return norm
        except Exception:
            pass

    # Step 2: Intelligent search across title variants
    queries = [
        allanime_show.get("name"),
        allanime_show.get("englishName"),
    ]
    seen = set()
    for query in queries:
        query = str(query or "").strip()
        if not query or query.lower() in seen:
            continue
        seen.add(query.lower())
        results = search_anilist(token, query)
        matched = _choose_confident_match(allanime_show, results)
        if matched:
            matched["_match_source"] = "title"
            return matched
    return None


def _run_anilist_match_search(flags, ui, allanime_show, token):
    candidate = with_loading(
        "Finding AniList match…",
        _find_fuzzy_anilist_candidate,
        allanime_show,
        token,
    )
    if candidate:
        choice = _confirm_auto_anilist_match(flags, ui, allanime_show, candidate)
        if choice == "link":
            save_source_anilist_match(allanime_show, candidate)
            merged = _merge_anilist_into_allanime(allanime_show, candidate)
            src = candidate.get("_match_source")
            tag = "✓ Matched by ID" if src == "id" else "✓ Suggested match"
            set_action_feedback(merged, tag)
            return merged
        elif choice == "search":
            return _run_manual_anilist_match(flags, ui, allanime_show, token)
        elif choice == "back":
            return None

    # Step 3: Directly enter manual search with info message in footer
    return _run_manual_anilist_match(flags, ui, allanime_show, token, initial_error="No matching title found")


def _run_manual_anilist_match(flags, ui, allanime_show, token, initial_error=""):
    source_title = allanime_show.get("_allanime_name") or allanime_show.get("name") or ""
    query = source_title
    search_error = initial_error
    while True:
        query = tui_pick(
            flags, ui, "Match AniList",
            [],
            header_fn=_manual_anilist_input_header(allanime_show, error=search_error),
            return_query_on_enter=True,
            initial_query=query,
            is_search=True,
            help_dict=search_input_help(),
        )
        if query == -2 or not query:
            return None
        query = str(query).strip()
        if not query:
            continue
        search_error = ""
        try:
            results = with_loading(
                "Searching AniList…",
                search_anilist,
                token,
                query,
                True,
            )
        except SearchFailure as exc:
            search_error = str(exc)
            continue
        if not results:
            search_error = f'No results found for "{query}"'
            continue
        options = [show.get("name", "Unknown") for show in results]
        idx = tui_pick(
            flags, ui, "Match AniList",
            options,
            header_fn=_search_result_header(
                "AniList", query, "sub",
                lambda: results, lambda: "", "cancel"
            ),
            top_header_fn=_search_cover_header(lambda: results),
            help_dict=picker_help("Link title", "Search again", "Cancel"),
        )
        if idx == -2:
            return None
        if idx == -3:
            continue
        if 0 <= idx < len(results):
            chosen = results[idx]
            chosen["_match_source"] = "manual"
            save_source_anilist_match(allanime_show, chosen)
            merged = _merge_anilist_into_allanime(allanime_show, chosen)
            set_action_feedback(merged, "✓ Linked title")
            return merged

def match_allanime_show_to_anilist(flags, ui, allanime_show, token, manual_on_fail=False):
    show_id = str(allanime_show.get("_id") or allanime_show.get("id") or "")
    stored = get_source_anilist_match(show_id) if show_id else {}
    stored_id = str(stored.get("_id") or "")
    provider_al_id = str(allanime_show.get("aniListId") or "")

    # Priority 1: Stored 1:1 match from local storage
    if stored_id:
        try:
            media = fetch_anilist_media(token, stored_id)
            if media:
                match_source = stored.get("match_source") or "stored"
                allanime_show["_match_source"] = match_source
                normalized_media = anilist_normalize.normalize_media(media)
                save_source_anilist_match(allanime_show, normalized_media)
                merged = _merge_anilist_into_allanime(allanime_show, normalized_media)
                set_action_feedback(merged, "✓ Found saved match")
                return merged
        except Exception:
            pass

    # Priority 2: Exact provider aniListId
    if provider_al_id:
        try:
            media = fetch_anilist_media(token, provider_al_id)
            if media:
                allanime_show["_match_source"] = "id"
                normalized_media = anilist_normalize.normalize_media(media)
                save_source_anilist_match(allanime_show, normalized_media)
                merged = _merge_anilist_into_allanime(allanime_show, normalized_media)
                set_action_feedback(merged, "✓ Matched by ID")
                return merged
        except Exception:
            pass # fallback to title search if fetching exact media fails

    # Priority 3: Title search & fuzzy match
    queries = [
        allanime_show.get("name"),
        allanime_show.get("englishName"),
    ]
    seen = set()
    for query in queries:
        query = str(query or "").strip()
        if not query or query.lower() in seen:
            continue
        seen.add(query.lower())
        results = search_anilist(token, query)
        matched = _choose_confident_match(allanime_show, results)
        if matched:
            allanime_show["_match_source"] = "fuzzy"
            save_source_anilist_match(allanime_show, matched)
            merged = _merge_anilist_into_allanime(allanime_show, matched)
            set_action_feedback(merged, "✓ Suggested match")
            return merged

    # Priority 4: Manual Picker
    if manual_on_fail:
        return _run_manual_anilist_match(flags, ui, allanime_show, token)
    return None

# ── Platform ──────────────────────────────────────────────────────────────────
def is_termux():
    return (os.environ.get("PREFIX","").startswith("/data/data/com.termux")
            or os.path.exists("/data/data/com.termux"))

def check_deps():
    needed = ["openssl"] + (["am"] if is_termux() else ["mpv"])
    for p in needed:
        if not shutil.which(p):
            err(f"'{p}' not found.")
            sys.exit(1)

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def extract_franchise_query(title: str) -> str:
    if not title:
        return ""
    from allmanga_cli.brain import AnimeBrain
    try:
        bout = AnimeBrain.process(str(title).strip(), dict)
        franchise = bout.get("franchise")
        if franchise:
            clean = franchise.split(":")[0].split(" - ")[0].strip()
            clean = re.sub(r"^[-\s_:]+|[-\s_:]+$", "", clean).strip()
            if clean and len(clean) >= 3:
                return clean
    except Exception:
        pass

    t = str(title).strip()
    t = re.sub(r"(?i)\s*\((?:season|part|cour|tv|the)\b.*?\)", "", t)
    t = re.sub(r"(?i)\s*[:–-]\s*(?:season|part|cour|the final|s\d+)\b.*$", "", t)
    t = re.sub(r"(?i)\s+(?:\d+(?:st|nd|rd|th)?\s+season|season\s+\d+|part\s+\d+|cour\s+\d+|s\d+)\b.*$", "", t)
    t = re.sub(r"(?i)\s+(?:[ivx]+|\d+)\s*$", "", t)
    return t.strip()


def extract_matching_queries(anilist_show: dict) -> list[str]:
    queries = []

    # 1. Franchise base queries (both Romaji and English)
    for key in ("name", "englishName"):
        val = str(anilist_show.get(key) or "").strip()
        franchise = extract_franchise_query(val)
        if franchise and franchise not in queries and len(franchise) >= 3:
            queries.append(franchise)

    # 2. Full primary and english names
    for key in ("name", "englishName"):
        val = str(anilist_show.get(key) or "").strip()
        if val and val not in queries:
            queries.append(val)

    # 3. Native title
    nat = str(anilist_show.get("nativeName") or "").strip()
    if nat and nat not in queries:
        queries.append(nat)

    # 4. Synonyms / AltNames
    for alt in (anilist_show.get("altNames") or anilist_show.get("synonyms") or []):
        alt_str = str(alt or "").strip()
        if not alt_str:
            continue
        alt_franchise = extract_franchise_query(alt_str)
        if alt_franchise and alt_franchise not in queries and len(alt_franchise) >= 3:
            queries.append(alt_franchise)
        if alt_str not in queries:
            queries.append(alt_str)

    return queries


def match_anilist_show_to_provider(anilist_show, ttype="sub", provider_id=None, status_cb=None):
    def _notify(msg):
        if callable(status_cb):
            try:
                status_cb(msg)
            except Exception:
                pass

    al_id = str(anilist_show.get("_id") or anilist_show.get("id") or "")
    stored = get_al_match(al_id) if al_id else {}
    stored_pid = stored.get("_provider") or stored.get("provider")

    # If stored provider is inactive, broken, or disabled, ignore it to trigger default provider fallback
    if stored_pid and not is_provider_active(stored_pid):
        stored_pid = None

    if not provider_id:
        provider_id = stored_pid or _DEFAULT_PROVIDER_ID

    provider_id = provider_key(provider_id)
    p_name = provider_display_name(provider_id)

    # Priority 1: Check saved 1:1 match for this provider
    if al_id and stored and stored.get("_id") and stored_pid == provider_id:
        _notify("Locating saved match…")
        direct = get_show_by_id(stored["_id"], provider_id=stored_pid)
        if direct:
            direct_name = str(direct.get("name") or "").strip()
            if direct_name and direct_name != al_id:
                _notify("Match found")
                direct["_match_source"] = stored.get("match_source") or "stored"
                return _merge_anilist_into_allanime(direct, anilist_show)

    # Priority 2: Direct AniList ID lookup (for AniList-native providers like Anikoto, Miruro)
    if al_id and provider_id in ("anikoto", "miruro"):
        _notify("Verifying ID…")
        try:
            direct = get_show_by_id(al_id, provider_id=provider_id)
            if direct:
                d_al = str(direct.get("aniListId") or "")
                d_id = str(direct.get("_id") or "")
                if (d_al and d_al == al_id) or (d_id and d_id == al_id):
                    _notify("Match found")
                    direct["_match_source"] = "id"
                    save_al_match(al_id, direct)
                    return _merge_anilist_into_allanime(direct, anilist_show)
        except Exception:
            pass

    # Priority 3: Search queries on provider catalog
    queries = extract_matching_queries(anilist_show)
    seen_queries = set()
    p_shows = []
    query_count = 0
    for query in queries:
        q_lower = query.strip().lower()
        if not q_lower or q_lower in seen_queries:
            continue
        seen_queries.add(q_lower)
        query_count += 1

        if query_count == 1:
            _notify(f"Finding streams on {p_name}…")
        else:
            _notify("Trying alternate titles…")

        results = search_anime(query, ttype, provider_id=provider_id)
        if results:
            exact = next((p for p in results if al_id and str(p.get("aniListId") or "") == al_id), None)
            if exact:
                _notify("Match found")
                exact["_match_source"] = "id"
                save_al_match(al_id, exact)
                return _merge_anilist_into_allanime(exact, anilist_show)
            p_shows.extend(results)

    # Priority 4: Fuzzy scored match
    if p_shows:
        _notify("Finding the best match…")
        seen_ids = set()
        unique_shows = []
        for show in p_shows:
            sid = show.get("_id")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                unique_shows.append(show)

        matched = _best_allanime_match(anilist_show, unique_shows)
        if matched:
            _notify("Match found")
            matched["_match_source"] = "fuzzy"
            save_al_match(al_id, matched)
            return _merge_anilist_into_allanime(matched, anilist_show)

    return None

match_anilist_show_to_allanime = match_anilist_show_to_provider

# ── API ───────────────────────────────────────────────────────────────────────
def _allanime_provider():
    return get_provider(provider_key(), _req)


def _provider_for_title(show):
    return get_provider(title_provider_key(show), _req)


def search_anime(query, ttype="sub", raise_errors=False, provider_id=None):
    provider_id = provider_key(provider_id)
    provider_name = provider_display_name(provider_id)
    try:
        return get_provider(provider_id, _req).search(query, ttype)
    except SearchFailure as e:
        debug_warn(f"{provider_name} search failed", e)
        if raise_errors:
            raise
        return []
    except Exception as e:
        debug_warn(f"{provider_name} search failed", e)
        if raise_errors:
            failure = SearchFailure(search_failure_message(provider_name, e))
            raise failure from e
        return []

def get_show_by_id(show_id, provider_id=None):
    provider_id = provider_key(provider_id)
    try:
        return get_provider(provider_id, _req).get_title(show_id)
    except Exception as e:
        debug_warn(f"{provider_id} show fetch failed", e)
        return None

def get_allanime_show(show_id):
    return get_show_by_id(show_id)

def fetch_episode_catalog(show_id, ttype="sub", provider_id=None):
    return get_provider(provider_id, _req).episode_catalog(show_id, ttype)

def fetch_episode_ids(show_id, ttype="sub"):
    """Compatibility wrapper; use fetch_episode_catalog() for state details."""
    return fetch_episode_catalog(show_id, ttype)["ids"]

def update_available_count_from_episode_ids(show, ttype, episode_ids, detail=None, labels=None):
    from allmanga_cli.domain.episodes import highest_episode_number
    if not show or not ttype or episode_ids is None:
        return False
    available = dict(show.get("availableEpisodes") or {})
    changed = False

    if detail:
        for key, ids in detail.items():
            if key in ("sub", "dub") and isinstance(ids, list):
                existing_count = available.get(key, 0)
                new_count = highest_episode_number(ids)
                if str(new_count) != str(existing_count):
                    available[key] = new_count
                    changed = True
    else:
        existing_count = available.get(ttype, 0)
        new_count = highest_episode_number(episode_ids)
        if str(new_count) != str(existing_count):
            available[ttype] = new_count
            changed = True

    old_ids = show.get("_episode_ids") or []
    old_ttype = show.get("_episode_ids_ttype")
    if old_ids != list(episode_ids) or old_ttype != ttype:
        changed = True

    show["availableEpisodes"] = available
    show["_episode_ids"] = list(episode_ids)
    show["_episode_ids_ttype"] = ttype
    if labels is not None:
        show["_episode_labels"] = {
            str(key): str(value)
            for key, value in dict(labels or {}).items()
            if str(key) and str(value)
        }
        show["_episode_labels_ttype"] = ttype
    return changed

def ensure_episode_ids(show, ttype):
    if not show:
        return []
    cached_ttype = show.get("_episode_ids_ttype")
    cached_ids = (
        _normalize_episode_ids(show.get("_episode_ids"))
        if cached_ttype == ttype else []
    )
    cached_state = (
        str(show.get("_episode_catalog_state") or "")
        if cached_ttype == ttype else ""
    )
    if cached_state == "loaded":
        update_available_count_from_episode_ids(show, ttype, cached_ids)
        return cached_ids

    legacy_ids = cached_ids
    if legacy_ids and not cached_state:
        cached_state = (
            "legacy_contiguous"
            if _is_contiguous_legacy_catalog(legacy_ids)
            else "loaded"
        )
        if cached_state == "loaded":
            show["_episode_catalog_state"] = "loaded"
            update_available_count_from_episode_ids(show, ttype, legacy_ids)
            return legacy_ids

    show_id = title_provider_id(show)
    if show_id and str(show_id).startswith("local:"):
        eps = show.get("availableEpisodesDetail", {}).get(ttype, [])
        return _normalize_episode_ids(eps)

    if show_id:
        enrich_show_if_missing(show)
        catalog = _provider_for_title(show).episode_catalog(show_id, ttype)
    else:
        catalog = {
            "state": "unavailable",
            "ids": [],
            "error": "This title has no provider ID for episode lookup.",
        }

    if catalog["state"] == "loaded":
        show["_episode_catalog_state"] = "loaded"
        show.pop("_episode_catalog_error", None)
        update_available_count_from_episode_ids(
            show,
            ttype,
            catalog["ids"],
            catalog.get("detail"),
            catalog.get("labels"),
        )
        return catalog["ids"]

    show["_episode_ids_ttype"] = ttype
    show["_episode_catalog_error"] = catalog["error"]
    if legacy_ids:
        show["_episode_ids"] = legacy_ids
        show["_episode_catalog_state"] = "legacy_contiguous"
        return legacy_ids

    show.pop("_episode_ids", None)
    show["_episode_catalog_state"] = "unavailable"
    return []

def check_translation_switch_capability(show, current_ttype, target_ttype):
    p_id = (show or {}).get("_provider") or (show or {}).get("_provider_name")
    from allmanga_cli.providers import provider_translation_capability
    return provider_translation_capability(p_id, show, current_ttype, target_ttype)


def episode_catalog_needs_fetch(show, ttype):
    if not show:
        return False
    if show.get("_episode_ids_ttype") != ttype:
        return True
    state = str(show.get("_episode_catalog_state") or "")
    if state == "loaded":
        return False
    ids = _normalize_episode_ids(show.get("_episode_ids"))
    return not ids or _is_contiguous_legacy_catalog(ids)

def load_episode_ids_for_selection(show, ttype):
    if episode_catalog_needs_fetch(show, ttype):
        return with_loading(
            "Loading episode list...",
            ensure_episode_ids,
            show,
            ttype,
        )
    return ensure_episode_ids(show, ttype)

def episode_catalog_error(show):
    p_name = (show.get("_provider_name") or show.get("_provider") or "").title() if show else "this provider"
    return str(
        (show or {}).get("_episode_catalog_error")
        or f"No episodes available on {p_name}. Try another provider."
    )

def get_episode_data(show_id, ep, ttype="sub", provider_id=None):
    provider_id = provider_key(provider_id)
    try:
        return get_provider(provider_id, _req).episode_sources(show_id, ep, ttype)
    except ProviderDependencyError as exc:
        from allmanga_cli.ui.display import exit_alt_screen
        import sys
        exit_alt_screen()
        sys.stderr.write(f"{exc}\n")
        sys.stderr.flush()
        sys.exit(1)
    except Exception as e:
        err(f"Episode fetch failed: {e}"); return None

def get_clock_links(path):
    try:
        return allanime_service.get_clock_links(_req, path)
    except Exception:
        return []


# ── Background resolver ───────────────────────────────────────────────────────
# Stream pool + background resolver live in core.streams; aliases below keep
# existing callers (app/playback.py, app/search.py, tests) working unchanged.
all_streams = streams.all_streams
_streams_lock = streams._streams_lock
_bg_lock = streams._bg_lock
_clear_streams = streams._clear_streams
_extend_streams = streams._extend_streams
_stream_snapshot = streams._stream_snapshot
_stream_count = streams._stream_count
_publish_stream = streams._publish_stream
_generation_is_current = streams._generation_is_current
_update_bg_stats = streams._update_bg_stats
start_bg_resolve = streams.start_bg_resolve

def _redraw_player(props):
    try:
        from allmanga_cli.ui.player_screen import update_mpv_props
        update_mpv_props(props)
    except ImportError:
        pass


_ipc_player = MpvIpc(_redraw_player)
atexit.register(_ipc_player.quit)

def play_desktop(title, ep, stream, fetch_callback=None, total_eps=1, is_binge=False, show_id=None, osd_msg="", episode_index=0, next_episode=None, mal_id=None, aniskip_enabled=True, aniskip_auto=True):
    return desktop_playback.play_desktop(
        _ipc_player,
        title,
        ep,
        stream,
        get_resume_time=get_resume_time,
        get_preferred_mirror=get_preferred_mirror,
        update_stream_info=lambda info: _player_ui_state.__setitem__(
            "stream_info", info
        ),
        fetch_callback=fetch_callback,
        total_eps=total_eps,
        is_binge=is_binge,
        show_id=show_id,
        osd_msg=osd_msg,
        episode_index=episode_index,
        next_episode=next_episode,
        mal_id=mal_id,
        aniskip_enabled=aniskip_enabled,
        aniskip_auto=aniskip_auto,
    )
def play_local_video(path, player="mpv"):
    return local_playback.play_local_video(
        path,
        player,
        termux=is_termux(),
        error=err,
    )



# ── Main ──────────────────────────────────────────────────────────────────────

fetch_episode_stream = streams.fetch_episode_stream

def trigger_migration(old_dir_full, new_dir):
    from allmanga_cli.core.storage import load_downloads_db
    import shutil, os
    db = load_downloads_db()
    
    if os.path.isdir(old_dir_full) and os.path.abspath(old_dir_full) != os.path.abspath(new_dir):
        ans = input(f"Move existing downloads from {old_dir_full} to {new_dir}? [y/N]: ").strip().lower()
        if ans == "y":
            print(f"Moving downloads to {new_dir}...")
            try:
                os.makedirs(new_dir, exist_ok=True)
                moved_anything = False
                shows = db.get("shows", {})
                for title in shows.keys():
                    s = os.path.join(old_dir_full, title)
                    d = os.path.join(new_dir, title)
                    if os.path.isdir(s):
                        shutil.move(s, d)
                        moved_anything = True
                
                if moved_anything and os.path.basename(old_dir_full.rstrip(os.sep)) == "allmanga-cli":
                    try:
                        os.rmdir(old_dir_full)
                        print(f"Cleaned up empty folder: {old_dir_full}")
                    except OSError:
                        pass
                        
                print("Migration complete!")
            except Exception as e:
                err(f"Failed to migrate files: {e}")

def handle_config_command(args):
    from allmanga_cli.core.storage import load_config, save_config
    import shutil
    cfg = load_config()
    
    if args.config_action == "set":
        key = args.config_key
        val = args.config_value
        
        if key == "download_dir":
            old_dir = cfg.get("download_dir", "")
            new_dir = os.path.expanduser(str(val or "").strip())
            
            if not new_dir:
                err("download_dir requires a value.")
                return
                
            if not new_dir.endswith("allmanga-cli"):
                ans_append = input(f"Create 'allmanga-cli' subfolder in {new_dir}? [Y/n]: ").strip().lower()
                if ans_append != 'n':
                    new_dir = os.path.join(new_dir, "allmanga-cli")
                    val = os.path.join(str(val or "").strip(), "allmanga-cli")
            
            if not old_dir:
                from allmanga_cli.core.storage import get_default_download_dir
                old_dir_full = get_default_download_dir()
            else:
                old_dir_full = os.path.expanduser(old_dir)
                
            trigger_migration(old_dir_full, new_dir)
            cfg["download_dir"] = val
            save_config(cfg)
            from allmanga_cli.core.storage import load_downloads_db, save_downloads_db
            db = load_downloads_db()
            db["current_download_dir"] = new_dir
            save_downloads_db(db)
            print(f"Config updated: {key} = {val}")
        else:
            cfg[key] = val
            save_config(cfg)
            print(f"Config updated: {key} = {val}")

_active_subprocesses = []

def register_subprocess(proc):
    if proc not in _active_subprocesses:
        _active_subprocesses.append(proc)

def unregister_subprocess(proc):
    if proc in _active_subprocesses:
        _active_subprocesses.remove(proc)

def kill_active_subprocesses():
    import os, signal
    for proc in _active_subprocesses:
        try:
            if os.name == 'posix':
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass

def main():
    def _force_exit(sig, frame):
        kill_active_subprocesses()
        try:
            restore_terminal()
        except Exception:
            pass
        os._exit(130)
            
    signal.signal(signal.SIGINT, _force_exit)

    args, pa = parse_cli_args()
    
    if not getattr(args, "config_action", None):
        from allmanga_cli.core.storage import load_downloads_db, save_downloads_db, load_config
        cfg = load_config()
        db = load_downloads_db()
        current_cfg_dir = cfg.get("download_dir", "")
        if current_cfg_dir:
            current_cfg_dir_full = os.path.expanduser(current_cfg_dir)
            db_dir_full = db.get("current_download_dir", "")
            if db_dir_full and os.path.abspath(db_dir_full) != os.path.abspath(current_cfg_dir_full):
                print(f"\n\033[93m[!] Detected download directory change in config from {db_dir_full} to {current_cfg_dir_full}\033[0m")
                globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
                trigger_migration(db_dir_full, current_cfg_dir_full)
            
            if db.get("current_download_dir") != current_cfg_dir_full:
                db["current_download_dir"] = current_cfg_dir_full
                save_downloads_db(db)
                
    if getattr(args, "completion_shell", None):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        if getattr(args, "completion_install", False):
            path = install_completion(args.completion_shell)
            print(f"Installed {args.completion_shell} completion:")
            print(path)
            if args.completion_shell == "bash":
                print("Restart your shell, or run: exec bash")
            elif args.completion_shell == "zsh":
                print("Ensure ~/.zfunc is in fpath, then run: compinit")
            elif args.completion_shell == "fish":
                print("Restart fish, or run: exec fish")
            return
        print(generate_completion(args.completion_shell), end="")
        return

    if getattr(args, "show_search_history", False):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        for query in load_search_history():
            print(query)
        return

    if getattr(args, "clear_search_history", False):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        clear_search_history()
        print("Search history cleared.")
        return

    if getattr(args, "config_action", None):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        handle_config_command(args)
        return

    if getattr(args, "list_providers", False):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        from allmanga_cli.providers import available_providers, _DEFAULT_PROVIDER_ID, get_provider_registry
        cfg = load_config()
        default_pid = cfg.get("provider", _DEFAULT_PROVIDER_ID)
        
        CYAN, GREEN, BOLD, RESET, RED, YELLOW, DIM = "\033[36m", "\033[32m", "\033[1m", "\033[0m", "\033[31m", "\033[33m", "\033[2m"
        
        registry = get_provider_registry()
        
        print(f"\n{BOLD}Available Streaming Providers:{RESET}\n")
        
        import shutil
        term_width = shutil.get_terminal_size((80, 20)).columns

        rows = []
        for pid in sorted(available_providers().keys()):
            meta = registry.get(pid, {})
            name = meta.get("name", pid.title())
            engine = meta.get("engine", "unknown")
            status = meta.get("status", "unknown")
            ptype = meta.get("type", "anime")
            langs = "/".join(meta.get("languages", ["sub"]))
            rows.append({"pid": pid, "name": name, "engine": engine, "status": status, "type": ptype, "langs": langs})
            
        w_id = max(max((len(r["pid"]) + 2 for r in rows), default=0), len("ID"))
        w_name = max(max((len(r["name"]) for r in rows), default=0), len("Name"))
        w_eng = max(max((len(r["engine"]) for r in rows), default=0), len("Engine"))
        w_stat = max(max((len(r["status"]) for r in rows), default=0), len("Status"))
        w_type = max(max((len(r["type"]) for r in rows), default=0), len("Type"))
        w_lang = max(max((len(r["langs"]) for r in rows), default=0), len("Languages"))
        
        spacing = 4
        
        show_type = True
        show_name = True
        show_engine = True
        
        def calc_total_len():
            l = 2 + w_id + spacing + w_stat + spacing + w_lang
            if show_name: l += w_name + spacing
            if show_engine: l += w_eng + spacing
            if show_type: l += w_type + spacing
            return l

        if calc_total_len() > term_width:
            show_type = False
        if calc_total_len() > term_width:
            show_name = False
        if calc_total_len() > term_width:
            show_engine = False
        
        # Header
        header = f"    {BOLD}{'ID'.ljust(w_id - 2 + spacing)}"
        if show_name: header += f"{'Name'.ljust(w_name + spacing)}"
        if show_engine: header += f"{'Engine'.ljust(w_eng + spacing)}"
        header += f"{'Status'.ljust(w_stat + spacing)}"
        if show_type: header += f"{'Type'.ljust(w_type + spacing)}"
        header += f"{'Languages'}{RESET}"
        
        print(header)
        print(f"  {DIM}{'-'*calc_total_len()}{RESET}")
        
        for r in rows:
            pid, name, engine, status, ptype, langs = r["pid"], r["name"], r["engine"], r["status"], r["type"], r["langs"]
            status_color = GREEN if status == "active" else RED
            
            if pid == default_pid:
                id_str = f"{GREEN}▸ {pid.ljust(w_id - 2)}{RESET}"
            else:
                id_str = f"  {CYAN}{pid.ljust(w_id - 2)}{RESET}"
                
            row_str = f"  {id_str}{' '*spacing}"
            if show_name: row_str += f"{name.ljust(w_name)}{' '*spacing}"
            
            if show_engine:
                engine_str = f"{YELLOW}{engine.ljust(w_eng)}{RESET}" if engine == "hybrid" else f"{engine.ljust(w_eng)}"
                if engine == "scraper": engine_str = f"{DIM}{engine.ljust(w_eng)}{RESET}"
                row_str += f"{engine_str}{' '*spacing}"
                
            row_str += f"{status_color}{status.ljust(w_stat)}{RESET}{' '*spacing}"
            if show_type: row_str += f"{ptype.ljust(w_type)}{' '*spacing}"
            row_str += f"{langs}"
            
            print(row_str)
        
        print()
        print(f"  {DIM}Note: Scrapers are brittle and may break often. APIs and Hybrids are recommended.{RESET}\n")
        return

    check_deps()
    cfg = load_config()
    from allmanga_cli.providers import _DEFAULT_PROVIDER_ID
    if getattr(args, "provider", None) is None:
        args.provider = cfg.get("provider", _DEFAULT_PROVIDER_ID)
    display._configure_spinner_from_config(cfg)

    runtime_flags.debug_mode = args.debug
    runtime_flags.incognito_mode = bool(args.incognito)
    if args.incognito and (args.download or args.downloads or args.login or args.logout):
        pa.error("--incognito cannot be combined with downloads, login, or logout")
    if args.incognito:
        args.no_sync = True
    runtime_flags.sync_force_on = bool(args.sync and not args.no_sync)
    runtime_flags.sync_force_off = bool(args.no_sync)
    if getattr(args, "cover", None) is not None:
        runtime_flags.show_image = bool(args.cover)
    else:
        runtime_flags.show_image = bool(cfg.get("cover", False))

    if args.json:
        q = " ".join(args.query)
        ttype = "dub" if args.dub else "sub"

        if args.anilist is not None:
            # -a was passed
            if args.anilist == "search":
                res = search_anilist(cfg.get("anilist_token"), q)
            elif args.anilist and args.anilist != "menu":
                res = fetch_anilist_list(cfg.get("anilist_token"), args.anilist.upper())
            else:
                res = fetch_anilist_list(cfg.get("anilist_token"), "CURRENT")
            print(json.dumps(res, indent=2))
        else:
            if not q:
                print(json.dumps({"error": "No query provided."}, indent=2))
            else:
                res = search_anime(
                    q,
                    ttype,
                    provider_id=args.provider,
                )
                print(json.dumps(res, indent=2))
        sys.exit(0)

    if args.logout:
        clear_anilist_token(cfg)
        print(f"{GREEN}Logged out of AniList.{RESET}")
        sys.exit(0)

    if getattr(args, "auth_status", False):
        print("\n".join(anilist_auth_status_lines(cfg)))
        sys.exit(0)

    if getattr(args, "auth_token", False):
        lines = anilist_auth_token_lines(cfg, raw=getattr(args, "auth_token_raw", False))
        if not lines:
            print("AniList token is not saved.", file=sys.stderr)
            sys.exit(1)
        print("\n".join(lines))
        sys.exit(0)

    if args.login:
        if anilist_token_storage_status(cfg) != "none":
            print("\n".join(anilist_auth_login_existing_lines(cfg)))
            sys.exit(0)
        print(f"\n{YELLOW}AniList login{RESET}")
        print("Open this link, sign in, and copy the token:")
        print("\033[4mhttps://anilist.co/api/v2/oauth/authorize?client_id=9857&response_type=token\033[0m")
        tkn = prompt_anilist_token()
        if tkn:
            storage = save_anilist_token(cfg, tkn)
            print(f"{GREEN}AniList token saved to {storage}.{RESET}")
        else:
            print(f"{RED}No token provided.{RESET}")
        sys.exit(0)

    from allmanga_cli.context import UiState, MachineState
    import allmanga_cli.app as handlers

    # ``runtime_flags`` (context.FLAGS) is the single shared CliFlags instance.
    # It was populated from argparse above; hand the same object to handlers so
    # mid-run mutations (e.g. disabling sync) stay visible process-wide.
    runtime_flags.spinner_style = display._spinner_style
    flags = runtime_flags
    ui = UiState()

    def warn_before_tui(message):
        print(f"\n{YELLOW}{message}{RESET}")
        for remaining in range(3, 0, -1):
            print(f"\rContinuing in {remaining}...", end="", flush=True)
            time.sleep(1)
        print("\rContinuing now.   ")

    if args.sync and not args.no_sync:
        if args.history or args.cont:
            warn_before_tui(
                "--sync only applies to searched titles. History and continue stay local."
            )
            args.sync = False
            flags.sync_force_on = False
        elif not cfg.get("anilist_token") and not args.anilist:
            warn_before_tui(
                "--sync needs AniList login. Sync is disabled for this session."
            )
            args.sync = False
            args.no_sync = True
            flags.sync_force_on = False
            flags.sync_force_off = True

    # If args.downloads is true, it is handled in the main state loop.

    def resolveTracking(ctx, args, cfg, show=None):
        show = show or get_ui_show(ui)

        if getattr(args, "no_sync", False):
            return False

        if getattr(args, "sync", False) and ctx == "SEARCH":
            return bool(cfg.get("anilist_token") and show and get_show_anilist_id(show))

        if ctx in ("ANILIST_BROWSE", "ANILIST_SEARCH", "ANILIST_AIRING"):
            return bool(cfg.get("anilist_token") and show and get_show_anilist_id(show))

        return False

    globals()["resolveTracking"] = resolveTracking

    # AniList user data requires a token. Normal AllAnime watching stays local.
    if args.anilist and not args.no_sync and not cfg.get("anilist_token"):
        print(f"\n{YELLOW}AniList tracking needs a token.{RESET}")
        print("Open this link, sign in, and copy the token:")
        print("\033[4mhttps://anilist.co/api/v2/oauth/authorize?client_id=9857&response_type=token\033[0m")
        tkn = prompt_anilist_token()
        if tkn:
            storage = save_anilist_token(cfg, tkn)
            print(f"{GREEN}AniList token saved to {storage}.{RESET}")
        else:
            print(f"{RED}No token provided. Tracking is disabled for this session.{RESET}")
            args.no_sync = True
            flags.sync_force_on = False
            flags.sync_force_off = True
    if cfg.get("anilist_token") and not args.no_sync:
        retry_queued_anilist_writes(cfg["anilist_token"])

    if args.episode and "-" in args.episode:
        _s, _e = args.episode.split("-")
        args.episode = _s.strip()
        globals()["_download_batch_end"] = int(_e)
    elif args.episode:
        args.episode = str(args.episode).strip()

    termux  = is_termux()
    if getattr(args, "dub", False):
        ttype = "dub"
    elif getattr(args, "sub", False):
        ttype = "sub"
    else:
        ttype = cfg.get("translation_type", "sub")
    ui.ui_ttype_ctx = ttype
    active_provider = getattr(args, "provider", None) or cfg.get("provider") or cfg.get("default_provider") or _DEFAULT_PROVIDER_ID
    ui.ui_provider_ctx = provider_key(active_provider)
    quality = args.quality or cfg.get("quality","1080p")

    ms = MachineState(
        query_str=" ".join(args.query) if args.query else "",
        just_searched=bool(args.query),
        anilist_search_parent="QUIT",
        download_batch_end=globals().get("_download_batch_end")
    )

    state = "SEARCH"

    if args.anilist is not None:
        if args.anilist == "search":
            state = "ANILIST_SEARCH"
        elif args.anilist == "airing":
            state = "ANILIST_AIRING"
            args.anilist = "menu"
        else:
            if not cfg.get("anilist_token"):
                print(f"\n{YELLOW}AniList account is not linked.{RESET}")
                print(f"Run {BOLD}./allmanga-cli --login{RESET} to authenticate.")
                sys.exit(1)
            state = "ANILIST_MENU"
    elif args.cont:
        hist = load_history()
        if hist:
            h = hist[0]
            show = h.get("show", {})
            prepare_show_display_state(show, h.get("translation_type", ttype))
            ms.show_id = show.get("_id")
            ms.show_title = get_show_display_title(show)
            _hist_ttype = h.get("translation_type", ttype)
            ms.total_eps = show.get("availableEpisodes", {}).get(_hist_ttype, 1)
            ms.current_ep = playback_ep_from_history_entry(h, _hist_ttype)
            episode_ids = ensure_episode_ids(show, _hist_ttype)
            ms.total_eps = len(episode_ids) or ms.total_eps
            ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep)
            set_ui_context(ui, show, _hist_ttype)
            if not episode_ids:
                err(episode_catalog_error(show))
                state = "HISTORY"
            elif ms.current_ep_index is None:
                err("Saved episode is not present in the current provider catalog.")
                state = "HISTORY"
            else:
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
                info(f"Continuing {ms.show_title}: EP {ms.current_ep}/{ms.total_eps}")
                state = "PLAY"
        else:
            warn("Watch history is empty.")
    elif args.downloads:
        state = "DOWNLOADS"
    elif args.history:
        state = "HISTORY"

    while state != "QUIT":
        cur_ttype = ui.ui_ttype_ctx if ui.ui_ttype_ctx is not None else ttype
        if state == "DOWNLOADS":
            from allmanga_cli.app.downloads import handle_downloads_state
            state = handle_downloads_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "SEARCH":
            state = handlers.handle_search_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "HISTORY":
            state = handlers.handle_history_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "ANILIST_MENU":
            state = handlers.handle_anilist_menu_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "ANILIST_AIRING":
            state = handlers.handle_anilist_airing_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "ANILIST_BROWSE":
            state = handlers.handle_anilist_browse_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "ANILIST_SEARCH":
            state = handlers.handle_anilist_search_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "DETAILS":
            state = handlers.handle_details_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "UPDATE_PROGRESS":
            state = handlers.handle_update_progress_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "UPDATE_STATUS":
            state = handlers.handle_update_status_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "UPDATE_SCORE":
            state = handlers.handle_update_score_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "EPISODE":
            state = handlers.handle_episode_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "PLAY":
            state = handlers.handle_play_state(flags, ui, ms, cfg, args, cur_ttype, quality, resolveTracking)
        elif state == "ACTION_MENU":
            state = handlers.handle_action_menu_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "MIRRORS":
            state = handlers.handle_mirrors_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "BROWSER_PLAY":
            state = handlers.handle_browser_play_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        else:
            err(f"Unknown state: {state}")
            state = "QUIT"

    _ipc_player.quit()
