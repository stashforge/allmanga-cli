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
    SearchFailure,
    anilist_account_cache_key,
    read_json_response,
    read_limited_response,
    search_failure_message,
)
from allmanga_cli.cli.args import (
    build_anilist_search_parser,
    build_command_parser,
    build_legacy_parser,
    parse_cli_args,
)
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
from allmanga_cli.state.config import (
    load_config_file,
    save_config_file,
    secure_permissions as _secure_permissions,
)
from allmanga_cli.state.io import atomic_write_json, write_private_text
from allmanga_cli.state.paths import (
    ANILIST_QUEUE_PATH,
    CONFIG_DIR as CFG_DIR,
    CONFIG_PATH as CFG_PATH,
    HISTORY_MAX,
    HISTORY_PATH,
    LOG_DIR,
    PLAYBACK_PATH,
    SEARCH_HISTORY_PATH,
    STATE_DIR,
)
from allmanga_cli.state import preferences as preference_state
from allmanga_cli.state import anilist_queue as anilist_queue_state
from allmanga_cli.state import lists as list_state
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
    clear_terminal_images as _clear_terminal_images,
    get_key as _get_key,
    loading_frame as _loading_frame,
    loading_line as _loading_line,
    match as _match,
    render_item as _render_item,
)
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
from allmanga_cli.services import allanime as allanime_service
from allmanga_cli.services import anilist as anilist_service

INCOGNITO_MODE = "--incognito" in sys.argv[1:]
_incognito_cache_dir = None

def is_incognito():
    return "--incognito" in sys.argv or globals().get("INCOGNITO_MODE", False)

def _cleanup_incognito_cache():
    global _incognito_cache_dir
    if _incognito_cache_dir:
        shutil.rmtree(_incognito_cache_dir, ignore_errors=True)
        _incognito_cache_dir = None

def cover_cache_dir():
    global _incognito_cache_dir
    if not is_incognito():
        return os.path.expanduser("~/.cache/allmanga-cli/covers/")
    if not _incognito_cache_dir:
        _incognito_cache_dir = tempfile.mkdtemp(prefix="allmanga-cli-incognito-")
        os.chmod(_incognito_cache_dir, 0o700)
    return _incognito_cache_dir

atexit.register(_cleanup_incognito_cache)

# ── ANSI ──────────────────────────────────────────────────────────────────────
GREEN  = "\033[1;32m"; YELLOW = "\033[1;33m"; RED   = "\033[1;31m"
CYAN   = "\033[1;36m"; BOLD   = "\033[1m";    RESET = "\033[0m"

_needs_redraw = True
def _handle_sigwinch(signum, frame):
    global _needs_redraw
    _needs_redraw = True

try:
    signal.signal(signal.SIGWINCH, _handle_sigwinch)
except Exception:
    pass

_player_ui_state = {
    "active": False,
    "show": None,
    "current_ep": 0,
    "total_eps": 0,
    "status_lines": [],
    "stream_info": {},
    "mpv_props": None
}

def _add_status(m, color="\033[94m"):
    s = _player_ui_state
    if s["active"]:
        s["status_lines"].append(f"{color}{m}\033[0m")
        if len(s["status_lines"]) > 8:
            s["status_lines"].pop(0)

        # Avoid circular import/name errors by looking up render_player_screen dynamically if needed
        # Actually it will be defined globally before it's used in the PLAY state.
        if "render_player_screen" in globals():
            globals()["render_player_screen"]()
        return True
    return False

def info(m):
    m = sanitize_terminal_text(m)
    if not _add_status(f"[INFO] {m}", "\033[94m"): print(f"\033[94m[INFO]\033[0m {m}")
def ok(m):
    m = sanitize_terminal_text(m)
    if not _add_status(f"[OK] {m}", "\033[92m"): print(f"\033[92m[OK]\033[0m {m}")
def warn(m):
    m = sanitize_terminal_text(m)
    if not _add_status(f"[WARN] {m}", "\033[93m"): print(f"\033[93m[WARN]\033[0m {m}")
def err(m):
    m = sanitize_terminal_text(m)
    if not _add_status(f"[ERR] {m}", "\033[91m"): print(f"\033[91m[ERR]\033[0m {m}", file=sys.stderr)
def debug_warn(context, exc):
    if "--debug" in sys.argv or globals().get("DEBUG_MODE", False):
        warn(f"{context}: {exc}")

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

# ── Banners ───────────────────────────────────────────────────────────────────
def print_app_banner():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    C, B, R = "\033[36m", "\033[1m", "\033[0m"
    line = f"{C}{'─'*48}{R}"
    print(f"{line}\n{C}{B}▶ allmanga-cli — Anime Stream Player{R}\n{line}")

def print_episode_header(title, ep, total):
    B, R, LG = "\033[1m", "\033[0m", "\033[38;5;248m"
    clean, sn, stype = _extract_title_parts(title)
    info_bits = []
    if sn:    info_bits.append(f"season {sn}")
    if stype: info_bits.append(stype)
    ep_str = f"episode {ep} / {total}"
    if info_bits:
        ep_str += f"  \u2022  {' \u2022 '.join(info_bits)}"
    print(f"\n\033[2;36mnow playing\033[0m\n{B}{clean}{R}")
    print(f"{LG}{ep_str}{R}")
    print()

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
_RST       = "\033[0m"


def buildEpStr(show, ttype):
    return format_progress(show) or format_available_episodes(show, ttype)

def buildYearStr(show):
    start_y = show.get("airedStart", {}).get("year") if show.get("airedStart") else None
    end_y = show.get("airedEnd", {}).get("year") if show.get("airedEnd") else None
    return format_years(start_y, end_y, show.get("status"))

def buildInfoMetadataLine(show, ttype, override_ep_str=None, local_only=False):
    return format_info_metadata_line(show, ttype, override_ep_str=override_ep_str, local_only=local_only)

def should_update_anilist_progress(existing_progress, watched_episode):
    if watched_episode is None:
        return False

    from allmanga_cli.domain.episodes import anilist_progress_target_for_episode
    target_progress = anilist_progress_target_for_episode(watched_episode, fallback=None)

    if target_progress is None:
        return False

    if existing_progress is None:
        return True
    try:
        return target_progress > int(existing_progress)
    except (TypeError, ValueError):
        return True

def sync_progress_and_checkpoint(token, title, progress, media_id, show, ttype, status=None):
    status = tracking_status_for_progress(show, progress) if status is None else status
    progress = tracking_progress_for_sync(show, progress, status)

    existing = show.get("_anilist_progress")
    prog_to_send = progress if should_update_anilist_progress(existing, progress) else None

    if not scrobble_anilist(
        token,
        title,
        prog_to_send,
        media_id=media_id,
        status=status,
        show=show,
    ):
        return False

    if progress is not None:
        apply_tracking_progress_local(show, progress, status)
    else:
        if status:
            show["_anilist_list"] = status
    show["_progress_authority"] = "AL"
    return True

def sync_watched_to_anilist(token, title, ep, media_id, show, ttype):
    return sync_progress_and_checkpoint(
        token, title, ep, media_id, show, ttype
    )

def save_and_sync_watched(show, episode, ttype, token, title, progress, media_id):
    save_history(show, episode, ttype)

    if not (token and title and media_id):
        set_action_feedback(show, f"Saved locally as EP {episode}.")
        return {"status": "local_saved"}

    from allmanga_cli.domain.episodes import anilist_progress_target_for_episode
    sync_prog = anilist_progress_target_for_episode(episode, fallback=progress)

    try:
        current_al = max(0, int(show.get("_anilist_progress") or 0))
    except (TypeError, ValueError):
        current_al = 0

    if sync_prog is None:
        # Fallback if invalid
        set_action_feedback(show, f"Saved locally as EP {episode}.")
        return {"status": "local_saved"}

    if sync_prog <= current_al:
        set_action_feedback(show, f"Saved locally as EP {episode}. AniList already ahead at EP {current_al}, sync skipped.")
        return {"status": "skipped", "anilist_target": sync_prog, "anilist_current": current_al}

    result = sync_watched_to_anilist(token, title, sync_prog, media_id, show, ttype)
    if result:
        set_action_feedback(show, f"Saved locally as EP {episode}. AniList synced as EP {sync_prog}.")
        return {"status": "synced", "anilist_target": sync_prog}
    else:
        set_action_feedback(show, f"Saved locally as EP {episode}. AniList sync failed.")
        return {"status": "failed"}

def set_action_feedback(show, msg):
    show["_action_feedback"] = msg
    show["_action_feedback_time"] = time.time()

def build_info_panel(show, ttype, w, parts, override_ep_str=None, main_title=None, local_only=False):
    C_T  = "\033[1;97m"
    C_D  = "\033[38;5;248m"
    R    = "\033[0m"

    prepare_show_display_state(show, ttype, show.get("_sync_enabled") if "_sync_enabled" in show else None)
    title = main_title if main_title else get_show_display_title(show)
    alt = get_display_titles(show, title)

    _t = lambda s: _truncate_display(s, max(1, w - 1))
    info_title_line = f"{C_T}{_t(title)}{R}"
    info_alt_title_line = f"{C_D}{_t(alt)}{R}" if alt else f"{C_D}No alternative title{R}"

    metadata = buildInfoMetadataLine(show, ttype, override_ep_str, local_only=local_only)
    if is_incognito():
        info_metadata_line = f"{_t(f'{YELLOW}INCOGNITO{C_D} • {metadata}')}{R}"
    else:
        info_metadata_line = f"{C_D}{_t(metadata)}{R}"

    parts.extend([info_title_line, info_alt_title_line, info_metadata_line])


def _request_poster_redraw():
    import allmanga_cli.ui.picker as _picker_mod
    _picker_mod._needs_redraw = True


_poster_manager = PosterManager(
    enabled=lambda: bool(globals().get("SHOW_IMAGE", False)),
    cache_dir=cover_cache_dir,
    hovered_show_id=lambda: globals().get("_hovered_show_id"),
    request_redraw=_request_poster_redraw,
    loading_frame=_loading_frame,
)


def _clear_poster_downloads():
    _poster_manager.clear_downloads()


def _poster_footer_line(show, default_text, width):
    return _poster_manager.footer_line(show, default_text, width)


def _poster_needs_tick(show):
    return _poster_manager.needs_tick(show)


def _get_poster(show):
    globals()["_hovered_show_obj"] = show
    return _poster_manager.get(show)


_alt_screen_active = False

def enter_alt_screen():
    global _alt_screen_active
    if not _alt_screen_active:
        sys.stdout.write("\033[?1049h\033[2J\033[?25l")
        sys.stdout.flush()
        _alt_screen_active = True

def exit_alt_screen():
    global _alt_screen_active
    if _alt_screen_active:
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()
        _alt_screen_active = False

def with_loading(msg, fn, *args, **kwargs):
    try:
        ts = os.get_terminal_size()
        w, h = ts.columns, ts.lines
    except OSError:
        w, h = 80, 24

    if len(msg) > w - 1:
        msg = msg[:w - 4] + "..."

    sys.stdout.write(f"\033[{h};1H\033[2K\033[36m{msg}\033[0m\033[?25l")
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return fn(*args, **kwargs)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        termios.tcflush(fd, termios.TCIFLUSH)
        # sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def render_anilist_menu_loading(status):
    enter_alt_screen()
    try:
        size = os.get_terminal_size()
        columns, rows = size.columns, size.lines
    except OSError:
        columns, rows = 80, 24
    sys.stdout.write(
        "\033[?25l" + anilist_menu_loading_frame(status, rows, columns)
    )
    sys.stdout.flush()

def load_anilist_browse(token, status):
    render_anilist_menu_loading(status)
    return with_loading(
        f"Loading AniList list: {status}",
        fetch_anilist_list,
        token,
        status,
    )

atexit.register(exit_alt_screen)

def _exit_player_screen(close_alt=False):
    if close_alt:
        exit_alt_screen()
    _player_ui_state["active"] = False

def _get_player_poster(show):
    if not show:
        return ""
    globals()["_hovered_show_id"] = show.get("_id") or show.get("id")
    return _get_poster(show) or ""

def render_player_screen():
    s = _player_ui_state
    if not s["active"]: return

    enter_alt_screen()

    try:
        w, h = os.get_terminal_size(sys.stdin.fileno())
    except Exception:
        w, h = 80, 24

    show = s["show"]
    title = get_show_display_title(show) if show else "Unknown"
    clean, sn, stype = _extract_title_parts(title)

    info_bits = []
    if sn: info_bits.append(f"Season {sn}")
    if s["current_ep"] and s["total_eps"]:
        info_bits.append(f"Episode {s['current_ep']}/{s['total_eps']}")
    ep_str = " \u2022 ".join(info_bits)

    si = s.get("stream_info", {})
    qual = si.get('quality')
    mirror = si.get('mirror')
    stream_str = ""
    if mirror and qual:
        pref_star = " \u2022 \033[33mPreferred \u2605" if si.get('is_pref') else ""
        stream_str = f"{mirror} \u2022 {qual}{pref_star}\033[0m"

    props = s.get("mpv_props")
    is_playing = (props is not None)

    def fmt_time(sec):
        if not sec: return "00:00"
        m, sec = divmod(int(sec), 60)
        if m >= 60:
            hr, m = divmod(m, 60)
            return f"{hr:02d}:{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"

    content = []
    if is_incognito():
        content.append("\033[1;33mINCOGNITO\033[0m")
        content.append("")

    if is_playing:
        state_str = "▌▌ Paused" if props.get("pause") else "▶ Playing"
        pt_sec = props.get("playback-time", 0) or 0
        dur_sec = props.get("duration", 0) or 0

        t = fmt_time(pt_sec)
        d = fmt_time(dur_sec)
        rem_sec = dur_sec - pt_sec if dur_sec > 0 else 0
        rem = fmt_time(rem_sec)

        bar_width = max(10, min(40, w - 4))
        filled = int((pt_sec / dur_sec) * bar_width) if dur_sec > 0 else 0
        bar = ("█" * filled) + ("░" * (bar_width - filled))

        content.append(f"\033[1;36m{state_str}\033[0m")
        content.append("")
        for tl in _wrap_title(clean, w - 4, 2).splitlines():
            content.append(f"\033[1;97m{tl}\033[0m")
        content.append("")
        content.append(f"\033[38;5;248m{ep_str}\033[0m")
        if stream_str:
            content.append("")
            content.append(f"\033[38;5;248m{stream_str}\033[0m")
        content.append("")
        content.append(f"\033[38;5;250m{bar}\033[0m")
        content.append("")
        content.append(f"\033[38;5;250m{t} / {d}\033[0m")
        content.append(f"\033[38;5;246mRemaining \u2022 {rem}\033[0m")
        content.append("")
        content.append("\033[38;5;244mQ Quit   Shift+Left Previous   Shift+Right Next\033[0m")
    else:
        content.append("\033[1;36mLoading stream...\033[0m")
        content.append("")
        for tl in _wrap_title(clean, w - 4, 2).splitlines():
            content.append(f"\033[1;97m{tl}\033[0m")
        content.append("")
        content.append(f"\033[38;5;248m{ep_str}\033[0m")
        content.append("")
        content.append("\033[38;5;246mStatus\033[0m")
        content.append("")
        for sl in s["status_lines"]:
            content.append(sl)

    poster_raw = _get_player_poster(show)
    native_poster = poster_raw if _poster_uses_native_protocol(poster_raw) else ""
    poster_lines = _poster_symbol_lines(poster_raw, POSTER_HEIGHT, w)
    out = []

    # 1. Reserve a fixed poster container.
    if poster_raw:
        for row in range(POSTER_HEIGHT):
            line = poster_lines[row] if row < len(poster_lines) else ""
            out.append(f"\033[2K{line}")

    # 2. Add content
    for line in content:
        out.append(f"\033[2K{_fit_terminal_line(line, w)}")
    if out:
        overlay = f"\033[1;1H{native_poster}" if native_poster else ""
        sys.stdout.write(
            "\033[H" + "\r\n".join(out) + "\033[J"
            + overlay + "\033[1;1H\033[?25l"
        )
        sys.stdout.flush()



def _atomic_write_json(path, data, indent=None):
    return atomic_write_json(
        path, data, indent=indent, disabled=is_incognito()
    )

def write_private_log(filename, content):
    if is_incognito() and not globals().get("DEBUG_MODE", False):
        return None
    return write_private_text(LOG_DIR, filename, content)

def write_exception_log(filename):
    return write_private_log(filename, traceback.format_exc())

_prefs_cache = None  # in-memory cache for playback prefs

def load_prefs() -> dict:
    global _prefs_cache
    if _prefs_cache is not None:
        return _prefs_cache
    if not os.path.exists(PLAYBACK_PATH): return {}
    try:
        with open(PLAYBACK_PATH) as f:
            _prefs_cache = json.load(f)
            return _prefs_cache
    except Exception as e:
        debug_warn("Failed to load playback prefs", e)
        if is_incognito():
            _prefs_cache = {}
            return _prefs_cache
        backup_path = f"{PLAYBACK_PATH}.bad-{int(time.time())}"
        try:
            os.replace(PLAYBACK_PATH, backup_path)
            warn(f"Playback prefs were invalid; moved them to {backup_path}")
        except Exception as move_error:
            debug_warn("Failed to move invalid playback prefs aside", move_error)
        _prefs_cache = {}
        return _prefs_cache

def save_prefs(prefs: dict):
    global _prefs_cache
    if is_incognito():
        return False
    _atomic_write_json(PLAYBACK_PATH, prefs)
    _prefs_cache = prefs
    return True

def get_preferred_mirror(show_id: str) -> dict:
    return preference_state.preferred_mirror(load_prefs(), show_id)

def toggle_preferred_mirror(show_id: str, sname: str, resolution: str):
    if is_incognito():
        return
    save_prefs(preference_state.toggle_preferred_mirror(
        load_prefs(), show_id, sname, resolution
    ))

def get_episode_order(show_id: str, default_order: str) -> str:
    return preference_state.episode_order(
        load_prefs(), show_id, default_order
    )

def toggle_episode_order(show_id: str, default_order: str) -> str:
    if is_incognito():
        return get_episode_order(show_id, default_order)
    prefs = load_prefs()
    new_order = preference_state.toggle_episode_order(
        prefs, show_id, default_order
    )
    save_prefs(prefs)
    return new_order

def get_title_sync_preference(show):
    if not show:
        return None
    return preference_state.title_sync_preference(load_prefs(), show)

def get_title_sync(show) -> bool:
    return get_title_sync_preference(show) is True

def set_title_sync(show, enabled: bool):
    if not show:
        return
    if is_incognito():
        show["_sync_enabled"] = False
        return
    save_prefs(preference_state.set_title_sync(
        load_prefs(), show, enabled
    ))
    show["_sync_enabled"] = bool(enabled)

def get_local_progress(show, ttype="sub"):
    return history_domain.local_progress(
        load_history(),
        show,
        ttype,
    )

def get_local_episode_label(show, ttype="sub"):
    entry = get_history_entry(show, ttype)
    if entry and "episode" in entry:
        return entry["episode"]
    return None

def get_history_entry(show, ttype="sub"):
    show_id = str((show or {}).get("_id") or "")
    if not show_id:
        return None
    return next((
        entry for entry in load_history()
        if str(entry.get("show", {}).get("_id") or "") == show_id
        and entry.get("translation_type", "sub") == ttype
    ), None)

def get_last_synced_progress(show, ttype="sub"):
    entry = get_history_entry(show, ttype)
    if not entry:
        return None
    value = entry.get("last_synced_progress")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None

def episode_id_for_progress(show, ttype, progress):
    import decimal
    try:
        numeric_prog = decimal.Decimal(str(progress))
        if numeric_prog < 0:
            numeric_prog = decimal.Decimal("0")
    except decimal.InvalidOperation:
        numeric_prog = None

    if numeric_prog == decimal.Decimal("0"):
        return "0"

    episode_ids = ensure_episode_ids(show, ttype)
    if not episode_ids:
        return str(progress)

    if str(progress) in episode_ids:
        return str(progress)

    if numeric_prog is not None:
        for eid in episode_ids:
            try:
                if decimal.Decimal(str(eid)) == numeric_prog:
                    return str(eid)
            except decimal.InvalidOperation:
                continue

    if show.get("_episode_catalog_state") == "loaded":
        return None
    return str(progress)

ANILIST_HISTORY_STRIP_KEYS = {
    "_anilist_context",
    "_anilist_progress",
    "_anilist_list",
    "_anilist_updated_at",
    "_anilist_media",
    "_progress_authority",
    "_sync_conflict",
    "_sync_enabled",
}

HISTORY_SHOW_STRIP_KEYS = ANILIST_HISTORY_STRIP_KEYS | {
    "_poster_raw",
    "_poster_status",
    "_poster_status_time",
    "_poster_failed",
    "availableEpisodesDetail",
}

def sanitize_show_for_history(show):
    stored = dict(show or {})
    for key in HISTORY_SHOW_STRIP_KEYS:
        stored.pop(key, None)
    return stored

def sanitize_history_list(history):
    clean_history = []
    for entry in history:
        clean_entry = {**entry, "show": sanitize_show_for_history(entry.get("show"))}
        show = clean_entry["show"]
        if "_anilist_id" in show:
            if "aniListId" not in show:
                show["aniListId"] = str(show["_anilist_id"])
            del show["_anilist_id"]
        clean_history.append(clean_entry)
    return clean_history

def write_history_progress(show, progress, ttype, *, last_synced=None, touch=False):
    global _history_cache
    if is_incognito():
        return None
    os.makedirs(STATE_DIR, exist_ok=True)

    import decimal
    try:
        if decimal.Decimal(str(progress)) < 0:
            progress = "0"
    except decimal.InvalidOperation:
        pass
    history = load_history()
    old = get_history_entry(show, ttype)
    timestamp = int(time.time()) if touch else int((old or {}).get("timestamp") or time.time())
    stored_show = sanitize_show_for_history(show)
    episode_id = episode_id_for_progress(show, ttype, progress)
    if episode_id is None:
        debug_warn(
            "Skipped history progress update",
            ValueError(f"No provider episode mapping for progress {progress}"),
        )
        return None
    entry = {
        "show": stored_show,
        "episode": episode_id,
        "translation_type": ttype,
        "timestamp": timestamp,
    }
    if last_synced is None and old and "last_synced_progress" in old:
        entry["last_synced_progress"] = old["last_synced_progress"]
    elif last_synced is not None:
        entry["last_synced_progress"] = max(0, int(last_synced))
    history = [
        item for item in history
        if not (
            str(item.get("show", {}).get("_id") or "") == str(show.get("_id") or "")
            and item.get("translation_type", "sub") == ttype
        )
    ]
    history.insert(0, entry)
    history = history[:HISTORY_MAX]
    _atomic_write_json(HISTORY_PATH, sanitize_history_list(history), indent=2)
    _history_cache = history
    show["_local_progress"] = progress
    return entry

def set_last_synced_progress(show, progress, ttype="sub"):
    local_progress = get_local_progress(show, ttype)
    write_history_progress(
        show,
        local_progress if local_progress is not None else progress,
        ttype,
        last_synced=progress,
        touch=False,
    )

def prepare_show_display_state(show, ttype="sub", sync_enabled=None):
    if not show:
        return show
    raw_anilist_show = bool(
        show.get("_anilist_list")
        and not show.get("_allanime_name")
        and not show.get("aniListId")
    )
    if raw_anilist_show:
        show["aniListId"] = str(show.get("_id"))
    if globals().get("SYNC_FORCE_OFF", False):
        sync_enabled = False
    elif sync_enabled is None and raw_anilist_show:
        sync_enabled = True
    elif sync_enabled is None and globals().get("SYNC_FORCE_ON", False) and show.get("aniListId"):
        sync_enabled = True
    elif sync_enabled is None:
        sync_enabled = get_title_sync(show)
    show["_sync_enabled"] = bool(sync_enabled)
    show["_local_progress"] = get_local_progress(show, ttype)
    show["_local_episode_label"] = get_local_episode_label(show, ttype)
    if not show.get("_progress_authority"):
        show["_progress_authority"] = "AL" if sync_enabled else "LOCAL"
    return show

def get_resume_time(show_id: str, ep: int) -> int:
    if is_incognito():
        return 0
    return preference_state.resume_time(load_prefs(), show_id, ep)

def save_resume_time(show_id: str, ep: int, time: int):
    if is_incognito():
        return
    save_prefs(preference_state.save_resume_time(
        load_prefs(), show_id, ep, time
    ))

def get_pending_completion(show_id: str) -> dict:
    if is_incognito():
        return {}
    return preference_state.pending_completion(load_prefs(), show_id)

def save_pending_completion(show_id: str, ep, progress_ep: int, next_ep, time_pos: int, duration: int):
    if is_incognito():
        return
    save_prefs(preference_state.save_pending_completion(
        load_prefs(),
        show_id,
        ep,
        progress_ep,
        next_ep,
        time_pos,
        duration,
    ))

def clear_pending_completion(show_id: str):
    if is_incognito():
        return
    save_prefs(preference_state.clear_pending_completion(
        load_prefs(), show_id
    ))

def get_al_match(al_id: str) -> dict:
    return preference_state.anilist_match(load_prefs(), al_id)

def save_al_match(al_id: str, aa_show: dict):
    if is_incognito():
        return
    save_prefs(preference_state.save_anilist_match(
        load_prefs(), al_id, aa_show
    ))

def get_source_anilist_match(show_id: str) -> dict:
    return preference_state.source_anilist_match(
        load_prefs(), show_id
    )

def save_source_anilist_match(aa_show: dict, anilist_show: dict):
    if is_incognito():
        return
    save_prefs(preference_state.save_source_anilist_match(
        load_prefs(), aa_show, anilist_show
    ))

def clear_al_match(al_id: str):
    if is_incognito():
        return
    save_prefs(preference_state.clear_anilist_match(
        load_prefs(), al_id
    ))

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

_history_cache = None  # in-memory cache for watch history
_search_history_cache = None  # in-memory cache for search history

def _preserve_invalid_state_file(path, label):
    if is_incognito():
        debug_warn(f"Invalid {label.lower()} left untouched in incognito mode", ValueError(path))
        return
    backup_path = f"{path}.bad-{int(time.time())}"
    try:
        os.replace(path, backup_path)
        warn(f"{label} was invalid; moved it to {backup_path}")
    except Exception as move_error:
        debug_warn(f"Failed to move invalid {label.lower()} aside", move_error)

def load_history():
    global _history_cache
    try:
        raw = list_state.load_json_list(
            HISTORY_PATH,
            _history_cache,
        )
        if _history_cache is None:
            _history_cache = sanitize_history_list(raw)
        return _history_cache
    except Exception as e:
        debug_warn("Failed to load watch history", e)
        _preserve_invalid_state_file(HISTORY_PATH, "Watch history")
        _history_cache = []
        return _history_cache

def save_history(show, episode, ttype):
    if is_incognito():
        return
    episode_ids = show.get("_episode_ids") or []
    if episode_ids:
        episode_index = episode_index_for_id(episode_ids, episode)
        if episode_index is None:
            debug_warn(
                "Skipped history update",
                ValueError(f"Episode ID {episode!r} is absent from the catalog"),
            )
            return

    progress = str(episode)
    show["_sync_enabled"] = get_title_sync(show)
    try:
        show["_progress_authority"] = "LOCAL"
        write_history_progress(show, progress, ttype, touch=True)
    except Exception as e:
        debug_warn("Failed to save watch history", e)

def delete_history_entry(show_id, ttype):
    if is_incognito():
        return False
    global _history_cache
    history, changed = list_state.delete_history_entry(
        load_history(),
        show_id,
        ttype,
    )
    if not changed:
        return False
    try:
        _atomic_write_json(HISTORY_PATH, sanitize_history_list(history), indent=2)
        _history_cache = history
        return True
    except Exception as e:
        debug_warn("Failed to delete history entry", e)
        return False

def fetch_anilist_media(token, media_id):
    try:
        return anilist_service.fetch_media(
            anilist_urlopen,
            read_json_response,
            token,
            media_id,
        )
    except Exception as e:
        debug_warn("Failed to refresh AniList media", e)
        return {}

def get_show_anilist_id(show):
    try:
        if show.get("_anilist_id"):
            return int(show.get("_anilist_id"))
        if show.get("aniListId"):
            return int(show.get("aniListId"))
        match = show.get("anilistMatch")
        if isinstance(match, dict) and match.get("id"):
            return int(match["id"])
        return None
    except (ValueError, TypeError):
        return None

def get_show_mal_id(show):
    try:
        return int(show.get("malId")) if show.get("malId") else None
    except (ValueError, TypeError):
        return None

def get_anilist_media_id(anime):
    return get_show_anilist_id(anime)

def update_anime_from_anilist_media(anime, media):
    return anilist_service.apply_media_update(anime, media)


def refresh_history_entry_from_anilist(entry, token):
    show = (entry or {}).get("show", {})
    media_id = get_anilist_media_id(show)
    if not token or not media_id or not show.get("_sync_enabled"):
        return False
    media = fetch_anilist_media(token, media_id)
    if not media:
        return False
    changed = update_anime_from_anilist_media(show, media)
    if changed and show.get("_anilist_progress") is not None:
        show["_progress_authority"] = "AL"
    return changed



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


def refresh_history_anilist_airing_batch(history_entries):
    import time
    from .services import anilist as anilist_service
    from .services.http import urllib, json, request_json
    now = int(time.time())

    # 1 hour cooldown
    COOLDOWN = 3600

    media_ids_to_fetch = []
    entry_map = {}

    for entry in history_entries:
        show = entry.get("show")
        if not show:
            continue

        al_id = get_show_anilist_id(show)
        if not al_id:
            continue

        last_checked = show.get("_anilist_airing_checked_at", 0)
        next_airing_at = show.get("_next_airing_at")
        status = str(show.get("_anilist_status") or show.get("status") or "").upper()

        needs_refresh = False
        if next_airing_at and next_airing_at <= now:
            needs_refresh = True
        elif last_checked == 0:
            needs_refresh = True
        elif status in ("RELEASING", "NOT_YET_RELEASED", "UNKNOWN", "") and (now - last_checked) > COOLDOWN:
            needs_refresh = True

        if needs_refresh:
            media_ids_to_fetch.append(str(al_id))
            if str(al_id) not in entry_map:
                entry_map[str(al_id)] = []
            entry_map[str(al_id)].append({"entry": entry, "old_next_airing_at": next_airing_at})

    if not media_ids_to_fetch:
        return False

    # Deduplicate IDs
    media_ids_to_fetch = list(set(media_ids_to_fetch))

    try:
        batch_results = anilist_service.fetch_media_batch(anilist_urlopen, read_json_response, media_ids_to_fetch)
    except Exception as e:
        debug_warn("AniList batch fetch failed", e)
        return False

    changed = False
    for al_id, media in batch_results.items():
        items = entry_map.get(str(al_id), [])
        for item in items:
            entry = item["entry"]
            old_next_airing_at = item["old_next_airing_at"]
            show = entry.get("show")
            if not show: continue

            show["_anilist_airing_checked_at"] = now
            changed = True

            airing = media.get("nextAiringEpisode")
            if airing:
                new_ep = airing.get("episode")
                new_time = airing.get("timeUntilAiring")
                new_at = airing.get("airingAt")
                if not new_at and new_time:
                    new_at = now + new_time
                if new_ep != show.get("_next_airing_ep"):
                    show["_next_airing_ep"] = new_ep
                if new_at != show.get("_next_airing_at"):
                    show["_next_airing_at"] = new_at
                if new_time != show.get("_next_airing_time"):
                    show["_next_airing_time"] = new_time
            else:
                show.pop("_next_airing_ep", None)
                show.pop("_next_airing_time", None)
                show.pop("_next_airing_at", None)

            new_count = media.get("episodes")
            if new_count is not None and new_count != show.get("_anilist_episode_count"):
                show["_anilist_episode_count"] = new_count

            new_status = media.get("status")
            if new_status and show.get("_anilist_status") != new_status:
                show["_anilist_status"] = new_status
                changed = True

            if old_next_airing_at and old_next_airing_at <= now:
                if refresh_history_entry_allanime_catalog(entry):
                    changed = True

    if changed:
        _atomic_write_json(HISTORY_PATH, sanitize_history_list(history_entries), indent=2)
    return changed

def refresh_history_entry_allanime_catalog(entry):
    import time
    show = (entry or {}).get("show", {})
    ttype = entry.get("translation_type", "sub")
    show_id = show.get("_id")

    changed = False
    if not show_id:
        return False

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

    return changed

def save_refreshed_history(history):
    global _history_cache
    if is_incognito():
        return False
    clean_history = sanitize_history_list(history)
    try:
        _atomic_write_json(HISTORY_PATH, clean_history, indent=2)
        _history_cache = clean_history
        return True
    except Exception as e:
        debug_warn("Failed to save refreshed history", e)
        return False

def patch_history_entry_show(show_id, ttype, updated_show):
    if not show_id or is_incognito():
        return False
    history = load_history()
    changed = False
    for entry in history:
        if entry.get("translation_type", "sub") == ttype:
            s = entry.get("show")
            if s and s.get("_id") == show_id:
                # Merge safe provider fields from updated_show into the disk's show object
                safe_keys = {
                    "status", "episodeCount", "availableEpisodes", "availableEpisodesDetail",
                    "name", "englishName", "nativeName", "thumbnail", "altNames",
                    "type", "season", "airedStart", "score",
                    "_episode_ids", "_episode_ids_ttype", "_episode_catalog_state", "_allanime_checked_at"
                }
                for k in safe_keys:
                    v = updated_show.get(k)
                    if v is not None and s.get(k) != v:
                        s[k] = v
                        changed = True
                break
    if changed:
        return save_refreshed_history(history)
    return False


def load_search_history():
    global _search_history_cache
    try:
        _search_history_cache = list_state.load_json_list(
            SEARCH_HISTORY_PATH,
            _search_history_cache,
        )
        return _search_history_cache
    except Exception as e:
        debug_warn("Failed to load search history", e)
        _preserve_invalid_state_file(SEARCH_HISTORY_PATH, "Search history")
        _search_history_cache = []
        return _search_history_cache

def save_search_history(query):
    global _search_history_cache
    if is_incognito():
        return
    query = query.strip()
    if not query:
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    history = list_state.update_search_history(
        load_search_history(),
        query,
        HISTORY_MAX,
    )
    try:
        _atomic_write_json(SEARCH_HISTORY_PATH, history, indent=2)
        _search_history_cache = history
    except Exception as e:
        debug_warn("Failed to save search history", e)

def format_history_entry(h):
    return history_domain.format_history_entry(
        h,
        prepare_display_state=prepare_show_display_state,
        get_local_progress=get_local_progress,
    )

def format_history_updated_time(h):
    return history_domain.format_relative_time((h or {}).get("timestamp"))

def history_entry_progress(entry):
    return history_domain.history_entry_progress(
        entry,
        prepare_display_state=prepare_show_display_state,
        get_local_progress=get_local_progress,
    )

def history_entry_category(entry):
    return history_domain.history_entry_category(
        entry,
        prepare_display_state=prepare_show_display_state,
        get_local_progress=get_local_progress,
    )

def filter_history_entries(history, mode):
    return history_domain.filter_history_entries(
        history,
        mode,
        prepare_display_state=prepare_show_display_state,
        get_local_progress=get_local_progress,
    )

def _secure_config_permissions():
    _secure_permissions(CFG_PATH)

def load_config():
    return load_config_file(
        CFG_PATH,
        disabled=is_incognito(),
        on_error=lambda exc: debug_warn("Failed to load config", exc),
        on_invalid=lambda path: warn(
            f"Config was invalid; moved it to {path}"
        ),
    )

def save_config(cfg):
    return save_config_file(CFG_PATH, cfg, disabled=is_incognito())

def prompt_anilist_token():
    return getpass.getpass(f"\n{BOLD}Paste AniList Token: {RESET}").strip()

# ── AniList Tracking ──────────────────────────────────────────────────────────
def scrobble_anilist(
        token,
        title,
        ep,
        media_id=None,
        status=None,
        show=None,
        started_at=None,
        completed_at=None):
    try:
        if media_id is None:
            media_id = anilist_service.search_media_id(
                anilist_urlopen,
                read_json_response,
                title,
            )

        return update_anilist_entry(
            token,
            int(media_id),
            progress=ep,
            status=status,
            show=show,
            started_at=started_at,
            completed_at=completed_at,
        )
    except Exception:
        return False

def _fuzzy_date_has_value(value):
    return bool(
        isinstance(value, dict)
        and value.get("year")
        and value.get("month")
        and (value.get("day") or value.get("date"))
    )

def _today_fuzzy_date():
    today = date.today()
    return {
        "year": today.year,
        "month": today.month,
        "day": today.day,
    }

def _anilist_date_updates(show, progress=None, status=None):
    updates = {}
    normalized_status = str(status or "").upper()
    try:
        progress_value = int(progress) if progress is not None else None
    except (TypeError, ValueError):
        progress_value = None
    should_start = (
        (progress_value is not None and progress_value > 0)
        or normalized_status in {"CURRENT", "REPEATING", "COMPLETED"}
    )
    if should_start and not _fuzzy_date_has_value(show.get("_anilist_started_at")):
        updates["started_at"] = _today_fuzzy_date()
    if (
        normalized_status == "COMPLETED"
        and not _fuzzy_date_has_value(show.get("_anilist_completed_at"))
    ):
        updates["completed_at"] = _today_fuzzy_date()
    return updates

def update_anilist_entry(
        token,
        media_id,
        progress=None,
        status=None,
        score=None,
        show=None,
        started_at=None,
        completed_at=None):
    if is_incognito():
        return False
    try:
        date_updates = _anilist_date_updates(show or {}, progress, status)
        if started_at is not None:
            date_updates["started_at"] = started_at
        if completed_at is not None:
            date_updates["completed_at"] = completed_at
        res = anilist_service.update_entry(
            anilist_urlopen,
            read_json_response,
            token,
            media_id,
            progress=progress,
            status=status,
            score=score,
            **date_updates,
        )
        if res.get("errors"):
            debug_warn("AniList update returned errors", res.get("errors"))
            return False
        entry = (res.get("data") or {}).get("SaveMediaListEntry") or {}
        if show is not None and entry:
            if entry.get("startedAt"):
                show["_anilist_started_at"] = entry["startedAt"]
            if entry.get("completedAt"):
                show["_anilist_completed_at"] = entry["completedAt"]
        _anilist_list_cache.clear()
        _anilist_search_cache.clear()
        return True
    except Exception as e:
        debug_warn("AniList update failed", e)
        return False

_anilist_queue_lock = threading.RLock()
_anilist_queue_cache = None
_anilist_write_lock = threading.Lock()
_anilist_write_condition = threading.Condition(_anilist_write_lock)
_anilist_active_mutations = set()
_anilist_work_items = []
_anilist_worker = None

def _load_anilist_queue():
    global _anilist_queue_cache
    with _anilist_queue_lock:
        try:
            _anilist_queue_cache = anilist_queue_state.load_records(
                ANILIST_QUEUE_PATH,
                _anilist_queue_cache,
            )
        except Exception as e:
            debug_warn("Failed to load AniList mutation queue", e)
            _preserve_invalid_state_file(ANILIST_QUEUE_PATH, "AniList mutation queue")
            _anilist_queue_cache = []
        return _anilist_queue_cache

def _save_anilist_queue(records):
    global _anilist_queue_cache
    if is_incognito():
        return False
    with _anilist_queue_lock:
        _atomic_write_json(ANILIST_QUEUE_PATH, records, indent=2)
        anilist_queue_state.secure_queue_file(ANILIST_QUEUE_PATH)
        _anilist_queue_cache = records
        return True

def _anilist_mutation_key(record):
    return anilist_queue_state.mutation_key(record)

def _enqueue_anilist_progress(media_id, title, progress, status, show, ttype,
                              pending_completion=None):
    date_updates = _anilist_date_updates(show or {}, progress, status)
    record = anilist_queue_state.make_progress_record(
        media_id,
        title,
        progress,
        status,
        show,
        ttype,
        pending_completion,
        date_updates=date_updates,
    )
    with _anilist_queue_lock:
        records = anilist_queue_state.replace_progress_record(
            _load_anilist_queue(),
            record,
        )
        _save_anilist_queue(records)
    return record

def _update_queued_mutation(mutation_id, **changes):
    with _anilist_queue_lock:
        records, changed = anilist_queue_state.update_record(
            _load_anilist_queue(),
            mutation_id,
            changes,
        )
        if changed:
            _save_anilist_queue(records)

def _remove_queued_mutation(mutation_id):
    with _anilist_queue_lock:
        _save_anilist_queue(anilist_queue_state.remove_record(
            _load_anilist_queue(),
            mutation_id,
        ))

def _checkpoint_queued_progress(record):
    return None

def _finish_queued_pending_completion(record):
    completion = record.get("pending_completion") or {}
    show_id = completion.get("show_id")
    episode = completion.get("episode")
    if not show_id or episode is None:
        return
    pending = get_pending_completion(show_id)
    if str(pending.get("episode")) != str(episode):
        return
    save_resume_time(show_id, episode, 0)
    clear_pending_completion(show_id)

def _run_anilist_callback(callback, label):
    if not callback:
        return
    try:
        callback()
    except Exception as e:
        debug_warn(f"AniList {label} callback failed", e)

def _run_queued_anilist_progress(record, token, show=None,
                                  on_success=None, on_failure=None):
    mutation_id = record["id"]
    success = False
    try:
        _update_queued_mutation(
            mutation_id,
            attempts=int(record.get("attempts") or 0) + 1,
            last_attempt_at=int(time.time()),
        )
        prog_val = record.get("progress")
        prog_int = int(prog_val) if prog_val is not None else None
        success = scrobble_anilist(
            token,
            record.get("title") or "",
            prog_int,
            media_id=record.get("media_id"),
            status=record.get("status"),
            show=show,
            started_at=record.get("started_at"),
            completed_at=record.get("completed_at"),
        )
        if success:
            if show is not None:
                if prog_int is not None:
                    apply_tracking_progress_local(
                        show, prog_int, record.get("status")
                    )
                else:
                    if record.get("status"):
                        show["_anilist_list"] = record.get("status")
                show["_progress_authority"] = "AL"
            else:
                _checkpoint_queued_progress(record)
            _finish_queued_pending_completion(record)
            _remove_queued_mutation(mutation_id)
            _run_anilist_callback(on_success, "success")
        else:
            _update_queued_mutation(mutation_id, last_error="AniList update failed")
            _run_anilist_callback(on_failure, "failure")
    except Exception as e:
        debug_warn("Queued AniList update failed", e)
        _update_queued_mutation(mutation_id, last_error=str(e))
        _run_anilist_callback(on_failure, "failure")
    finally:
        with _anilist_write_condition:
            _anilist_active_mutations.discard(mutation_id)
            _anilist_write_condition.notify_all()
    return success

def _anilist_write_worker():
    global _anilist_worker
    while True:
        with _anilist_write_condition:
            if not _anilist_work_items:
                _anilist_worker = None
                _anilist_write_condition.notify_all()
                return
            record, token, show, on_success, on_failure = _anilist_work_items.pop(0)
        _run_queued_anilist_progress(
            record, token, show, on_success, on_failure
        )

def _start_queued_anilist_progress(record, token, show=None,
                                   on_success=None, on_failure=None):
    global _anilist_worker
    mutation_id = record.get("id")
    with _anilist_write_condition:
        if not mutation_id or mutation_id in _anilist_active_mutations:
            return None
        _anilist_active_mutations.add(mutation_id)
        _anilist_work_items.append(
            (record, token, show, on_success, on_failure)
        )
        if _anilist_worker is None:
            _anilist_worker = threading.Thread(
                target=_anilist_write_worker,
                name="anilist-write-worker",
                daemon=True,
            )
            _anilist_worker.start()
        _anilist_write_condition.notify_all()
        return record

def queue_anilist_progress(token, title, progress, media_id, show, ttype,
                           status=None, on_success=None, on_failure=None,
                           pending_completion=None):
    if is_incognito():
        return None
    status = tracking_status_for_progress(show, progress) if status is None else status
    progress = tracking_progress_for_sync(show, progress, status)

    existing = show.get("_anilist_progress") if show else None
    prog_to_send = progress if should_update_anilist_progress(existing, progress) else None

    try:
        record = _enqueue_anilist_progress(
            media_id, title, prog_to_send, status, show, ttype,
            pending_completion=pending_completion,
        )
    except Exception as e:
        debug_warn("Could not persist AniList update", e)
        if on_failure:
            on_failure()
        return None
    return _start_queued_anilist_progress(
        record, token, show, on_success, on_failure
    )

def retry_queued_anilist_writes(token):
    if is_incognito():
        return 0
    if not token:
        return 0
    records = list(_load_anilist_queue())
    latest = {}
    for record in records:
        key = _anilist_mutation_key(record)
        previous = latest.get(key)
        if (previous and previous.get("pending_completion")
                and not record.get("pending_completion")):
            record["pending_completion"] = previous["pending_completion"]
        latest[key] = record
    records = sorted(
        latest.values(),
        key=lambda record: (int(record.get("created_at") or 0), record.get("id") or ""),
    )
    if len(records) != len(_load_anilist_queue()):
        _save_anilist_queue(records)
    started = 0
    for record in records:
        if _start_queued_anilist_progress(record, token):
            started += 1
    return started

def flush_anilist_writes(timeout=None):
    if is_incognito():
        return True
    timeout = ANILIST_TIMEOUT + 2 if timeout is None else max(0, float(timeout))
    deadline = time.monotonic() + timeout
    with _anilist_write_condition:
        while _anilist_active_mutations or _anilist_work_items:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _anilist_write_condition.wait(remaining)
        return True

def _reconcile_status(show, progress):
    return reconciliation_domain.reconcile_status(
        show,
        progress,
        _positive_int,
    )

def _import_anilist_progress(show, ttype, progress, *, authority="AL"):
    progress = max(0, int(progress or 0))
    if progress > 0 or get_history_entry(show, ttype):
        write_history_progress(show, progress, ttype, last_synced=progress, touch=False)
    show["_anilist_progress"] = progress
    show["_local_progress"] = progress
    show["_progress_authority"] = authority
    show.pop("_sync_conflict", None)
    return {"action": "imported", "progress": progress}

def _push_local_progress(show, ttype, token, progress):
    al_id = get_show_anilist_id(show)
    if not token or not al_id:
        return {"action": "failed", "progress": progress}
    status = _reconcile_status(show, progress)

    existing = show.get("_anilist_progress")
    prog_to_send = int(progress) if should_update_anilist_progress(existing, progress) else None

    if not update_anilist_entry(
        token,
        int(al_id),
        progress=prog_to_send,
        status=status,
        show=show,
    ):
        return {"action": "failed", "progress": progress}

    if progress is not None:
        apply_tracking_progress_local(show, int(progress), status)
    else:
        if status:
            show["_anilist_list"] = status

    show["_progress_authority"] = "AL"
    show.pop("_sync_conflict", None)
    return {"action": "pushed", "progress": int(progress) if progress is not None else None, "status": status}

def reconcile_progress(show, ttype, token, *, anilist_source=False, sync_enabled=True):
    local = get_local_progress(show, ttype)
    local_label = get_local_episode_label(show, ttype) or str(local if local is not None else 0)
    try:
        remote = max(0, int(show.get("_anilist_progress") or 0))
    except (TypeError, ValueError):
        remote = 0
    last = get_last_synced_progress(show, ttype)
    show.pop("_sync_conflict", None)
    decision = reconciliation_domain.decide_progress_reconciliation(
        local=local,
        remote=remote,
        last_synced=last,
        status=show.get("_anilist_list"),
        anilist_source=anilist_source,
        sync_enabled=sync_enabled,
    )
    action = decision["action"]

    if action in ("import", "push"):
        conflict = {
            "local": local_label,
            "anilist": decision.get("anilist", remote),
        }
        show["_sync_conflict"] = conflict
        show["_progress_authority"] = decision.get("authority", "LOCAL")
        return {"action": "conflict", **conflict}

    if action == "local":
        show["_local_progress"] = local
        show["_progress_authority"] = decision["authority"]
        return {"action": "local", "progress": decision["progress"]}
    if action == "equal":
        set_last_synced_progress(show, local, ttype)
        show["_progress_authority"] = "AL"
        return {"action": "equal", "progress": local}
    if action == "conflict":
        conflict = {
            "local": local_label,
            "anilist": decision["anilist"],
        }
        show["_sync_conflict"] = conflict
        show["_progress_authority"] = decision["authority"]
        return {"action": "conflict", **conflict}

    return {"action": "local", "progress": local}

_anilist_list_cache = {}
_anilist_search_cache = {}

def fetch_anilist_list(token, status=None, force_refresh=False):
    cache_key = (
        anilist_account_cache_key(token),
        str(status or "ALL").upper(),
    )
    if not force_refresh and cache_key in _anilist_list_cache:
        return _anilist_list_cache[cache_key]

    try:
        shows = anilist_service.fetch_list(
            anilist_urlopen,
            read_json_response,
            token,
            status,
        )
        _anilist_list_cache[cache_key] = shows
        return shows
    except Exception as e:
        debug_warn("Failed to fetch AniList list", e)
        return []

def search_anilist(token, query, raise_errors=False):
    cache_key = (
        anilist_account_cache_key(token),
        str(query or "").strip().casefold(),
    )
    if cache_key in _anilist_search_cache:
        return _anilist_search_cache[cache_key]

    try:
        shows = anilist_service.search(
            anilist_urlopen,
            read_json_response,
            token,
            query,
        )
        _anilist_search_cache[cache_key] = shows
        return shows
    except SearchFailure as e:
        debug_warn("AniList search failed", e)
        if raise_errors:
            raise
        return []
    except Exception as e:
        debug_warn("AniList search failed", e)
        if raise_errors:
            raise SearchFailure(search_failure_message("AniList", e)) from e
        return []

def make_allanime_oneshot_search(query, ttype):
    loading = True
    results = []
    error = ""
    cfg = load_config()
    token = cfg.get("anilist_token")

    def _fetch():
        nonlocal loading, results, error
        try:
            shows = None
            al_shows = None

            def _fetch_aa():
                nonlocal shows, error
                try:
                    shows = search_anime(query, ttype, raise_errors=True)
                except SearchFailure as exc:
                    error = str(exc)
                    shows = []
            def _fetch_al(): nonlocal al_shows; al_shows = search_anilist(token, query)

            threads = [threading.Thread(target=_fetch_aa)]
            if token: threads.append(threading.Thread(target=_fetch_al))

            for t in threads: t.start()
            for t in threads: t.join()

            if shows and token and al_shows:
                for s in shows:
                    stored = get_source_anilist_match(s.get("_id"))
                    stored_id = str(stored.get("_id") or "")
                    matched = next(
                        (candidate for candidate in al_shows
                         if str(candidate.get("_id") or "") == stored_id),
                        None,
                    ) if stored_id else None
                    if not matched:
                        matched = _choose_confident_match(s, al_shows)
                    if matched:
                        save_source_anilist_match(s, matched)
                        _merge_anilist_into_allanime(s, matched)

            if shows: results.extend(shows)
        except Exception as e:
            if not error:
                error = search_failure_message("AllAnime", e)
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

            msg = f"Searching AllAnime: {query}"
            return _loading_line(msg, w)
        return ""

    def get_error():
        return error

    def live_fn(q=""):
        opts = [f"{s.get('name')}" for s in results]
        return opts, get_loading(), not loading

    return live_fn, get_results, get_loading, get_error

def make_anilist_oneshot_search(token, initial_query):
    results = []
    loading = True
    error = ""

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

            q = initial_query
            max_q = w - 30
            if len(q) > max_q > 0:
                q = q[:max_q] + "..."

            return _loading_line(f"Searching AniList: {q}", w)
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
        parts.append(f"\033[38;5;250mSource: \033[1;97m{source_name}\033[0m")
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

def _search_result_header(source_name, query_str, ttype, get_results, get_loading, esc_action="quit"):
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

def _manual_match_input_header(anilist_title, error=""):
    def _hdr(si):
        C_K = "\033[38;5;244m"
        C_T = "\033[1;97m"
        R = "\033[0m"
        parts = [""]
        parts.append(f"{C_K}Search AllAnime and choose the correct stream title.{R}")
        parts.append(f"{C_T}{_truncate_display(anilist_title, 80)}{R}")
        parts.append(
            f"{C_K}{error}  │  Esc=cancel{R}"
            if error else f"{C_K}Enter=search  Esc=cancel{R}"
        )
        return "\n".join(parts)
    return _hdr

def _manual_anilist_input_header(source_title, error=""):
    def _hdr(si):
        C_K = "\033[38;5;244m"
        C_T = "\033[1;97m"
        R = "\033[0m"
        parts = [
            "",
            f"{C_K}Search AniList and choose the correct tracking title.{R}",
            f"{C_T}{_truncate_display(source_title, 80)}{R}",
        ]
        if error:
            parts.append(f"{C_K}{error}  │  Esc=cancel{R}")
        else:
            parts.append(f"{C_K}Enter=search  Esc=cancel{R}")
        return "\n".join(parts)
    return _hdr

def _run_manual_match_search(flags, ui, anilist_show, ttype):
    al_title = anilist_show.get("name") or anilist_show.get("englishName") or ""
    al_id = str(anilist_show.get("_id") or "")
    query = al_title
    search_error = ""
    while True:
        query = tui_pick(
            flags, ui, "Match AllAnime",
            [],
            header_fn=_manual_match_input_header(al_title, search_error),
            return_query_on_enter=True,
            initial_query=query,
            is_search=True,
            help_dict=search_input_help()
        )
        if query == -2 or not query:
            return None
        query = str(query).strip()
        if not query:
            continue
        search_error = ""

        live_fn, get_results, get_loading, get_error = make_allanime_oneshot_search(query, ttype)
        initial_opts = [s.get("name", "Unknown") for s in get_results()]
        idx = tui_pick(
            flags, ui, "Match AllAnime",
            initial_opts,
            header_fn=_search_result_header("AllAnime", query, ttype, get_results, get_loading),
            top_header_fn=_search_cover_header(get_results),
            live_fn=live_fn,
            help_dict=picker_help("Link title", "Search again", "Cancel")
        )
        if idx == -2:
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

def _run_manual_anilist_match(flags, ui, allanime_show, token):
    source_title = allanime_show.get("_allanime_name") or allanime_show.get("name") or ""
    query = source_title
    search_error = ""
    while True:
        query = tui_pick(
            flags, ui, "Match AniList",
            [],
            header_fn=_manual_anilist_input_header(source_title, search_error),
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
                f"Searching AniList: {query}",
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
            return _merge_anilist_into_allanime(allanime_show, chosen)

def match_allanime_show_to_anilist(flags, ui, allanime_show, token, manual_on_fail=False):
    provider_al_id = str(allanime_show.get("aniListId") or "")
    stored = get_source_anilist_match(allanime_show.get("_id"))
    stored_id = str(stored.get("_id") or "")

    # Priority 1: Exact provider aniListId
    if provider_al_id:
        try:
            media = fetch_anilist_media(token, provider_al_id)
            if media:
                allanime_show["_match_source"] = "id"
                normalized_media = anilist_service.normalize_media(media)
                save_source_anilist_match(allanime_show, normalized_media)
                return _merge_anilist_into_allanime(allanime_show, normalized_media)
        except Exception:
            pass # fallback to title search if fetching exact media fails

    queries = [
        stored.get("name"),
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

        # Priority 2: Stored Match
        if stored_id:
            match_source = stored.get("match_source") or "stored"
            if not provider_al_id or stored_id == provider_al_id or match_source == "manual":
                matched = next((show for show in results if str(show.get("_id") or "") == stored_id), None)
                if matched:
                    allanime_show["_match_source"] = match_source
                    save_source_anilist_match(allanime_show, matched)
                    return _merge_anilist_into_allanime(allanime_show, matched)

        # Priority 3: Fuzzy Confident Match
        matched = _choose_confident_match(allanime_show, results)
        if matched:
            allanime_show["_match_source"] = "fuzzy"
            save_source_anilist_match(allanime_show, matched)
            return _merge_anilist_into_allanime(allanime_show, matched)

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
def _merge_anilist_into_allanime(allanime_show, anilist_show):
    allanime_show["_allanime_name"] = allanime_show.get("name")
    allanime_show["_display_name"] = anilist_show.get("name") or allanime_show.get("name")
    allanime_show["_display_english_name"] = anilist_show.get("englishName") or allanime_show.get("englishName")
    allanime_show["_anilist_list"] = anilist_show.get("_anilist_list")
    allanime_show["_anilist_progress"] = anilist_show.get("_anilist_progress")
    allanime_show["_anilist_score"] = anilist_show.get("_anilist_score")

    match_source = allanime_show.get("_match_source") or "fuzzy"
    allanime_show["anilistMatch"] = {"id": anilist_show.get("_id"), "source": match_source}
    allanime_show["aniListId"] = str(anilist_show.get("_id") or "")

    if anilist_show.get("_next_airing_ep"):
        allanime_show["_next_airing_ep"] = anilist_show["_next_airing_ep"]
        allanime_show["_next_airing_time"] = anilist_show["_next_airing_time"]
        allanime_show["_next_airing_at"] = anilist_show.get("_next_airing_at")
    if not allanime_show.get("thumbnail") and anilist_show.get("thumbnail"):
        allanime_show["thumbnail"] = anilist_show["thumbnail"]
    return allanime_show

def match_anilist_show_to_allanime(anilist_show, ttype):
    al_id = str(anilist_show.get("_id") or "")
    stored = get_al_match(al_id) if al_id else {}

    queries = []
    if anilist_show.get("name"):
        queries.append(anilist_show["name"])
    if anilist_show.get("englishName"):
        queries.append(anilist_show["englishName"])

    seen_queries = set()
    aa_shows = []

    # Priority 1: Fresh exact AllAnime aniListId
    for query in queries:
        q_lower = query.strip().lower()
        if not q_lower or q_lower in seen_queries:
            continue
        seen_queries.add(q_lower)

        results = search_anime(query, ttype)
        if results:
            exact = next((aa for aa in results if str(aa.get("aniListId") or "") == al_id), None)
            if exact:
                exact["_match_source"] = "id"
                save_al_match(al_id, exact)
                return _merge_anilist_into_allanime(exact, anilist_show)
            aa_shows.extend(results)

    # Priority 2: Stored match, if valid
    if al_id and stored and stored.get("_id"):
        direct = get_allanime_show(stored["_id"])
        if direct:
            direct_al_id = str(direct.get("aniListId") or "")
            match_source = stored.get("match_source") or "stored"

            # Use it if the ID matches, or if it has no ID (we fallback to it since no fresh exact ID found),
            # or if the user explicitly picked it manually despite ID mismatch.
            if direct_al_id == al_id or not direct_al_id or match_source == "manual":
                direct["_match_source"] = match_source
                return _merge_anilist_into_allanime(direct, anilist_show)

    # Priority 3: Fuzzy confident match
    if aa_shows:
        # Deduplicate candidates by _id
        seen_ids = set()
        unique_shows = []
        for show in aa_shows:
            sid = show.get("_id")
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                unique_shows.append(show)

        matched = _best_allanime_match(anilist_show, unique_shows)
        if matched:
            matched["_match_source"] = "fuzzy"
            save_al_match(al_id, matched)
            return _merge_anilist_into_allanime(matched, anilist_show)

    # Priority 4: None / Manual picker fallback
    return None

# ── API ───────────────────────────────────────────────────────────────────────
def search_anime(query, ttype="sub", raise_errors=False):
    try:
        return allanime_service.search_anime(_req, query, ttype)
    except SearchFailure as e:
        debug_warn("AllAnime search failed", e)
        if raise_errors:
            raise
        err(f"Search failed: {e}")
        return []
    except Exception as e:
        debug_warn("AllAnime search failed", e)
        failure = SearchFailure(search_failure_message("AllAnime", e))
        if raise_errors:
            raise failure from e
        err(f"Search failed: {failure}")
        return []

def get_allanime_show(show_id):
    try:
        return allanime_service.get_show(_req, show_id)
    except Exception as e:
        debug_warn("AllAnime show fetch failed", e)
        return None

def fetch_episode_catalog(show_id, ttype="sub"):
    return allanime_service.fetch_episode_catalog(_req, show_id, ttype)

def fetch_episode_ids(show_id, ttype="sub"):
    """Compatibility wrapper; use fetch_episode_catalog() for state details."""
    return fetch_episode_catalog(show_id, ttype)["ids"]

def update_available_count_from_episode_ids(show, ttype, episode_ids, detail=None):
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

    show_id = show.get("_id")
    if show_id:
        catalog = fetch_episode_catalog(show_id, ttype)
    else:
        catalog = {
            "state": "unavailable",
            "ids": [],
            "error": "This title has no provider ID for episode lookup.",
        }

    if catalog["state"] == "loaded":
        show["_episode_catalog_state"] = "loaded"
        show.pop("_episode_catalog_error", None)
        update_available_count_from_episode_ids(show, ttype, catalog["ids"], catalog.get("detail"))
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
    return str(
        (show or {}).get("_episode_catalog_error")
        or "Episode catalog is unavailable. Try again later."
    )

def get_episode_data(show_id, ep, ttype="sub"):
    try:
        return allanime_service.get_episode_data(_req, show_id, ep, ttype)
    except Exception as e:
        err(f"Episode fetch failed: {e}"); return None

def get_clock_links(path):
    try:
        return allanime_service.get_clock_links(_req, path)
    except Exception:
        return []


# ── Background resolver ───────────────────────────────────────────────────────
# all_streams is the shared list for the current episode.
# Both _streams_lock and _bg_lock are used to synchronize access.
all_streams: list = []
_streams_lock = threading.Lock()  # guards all_streams reads/writes
_streams_generation = 0  # invalidates workers started for an older episode
_bg_thread = None  # type: Optional[threading.Thread]
_bg_lock = threading.Lock()  # guards _bg_thread and _bg_stats
_bg_generation = 0
_bg_stats = {"resolved": 0, "failed": 0, "total": 0, "current": ""}

def _clear_streams():
    global _streams_generation
    with _streams_lock:
        _streams_generation += 1
        all_streams.clear()
        return _streams_generation

def _extend_streams(streams):
    with _streams_lock:
        all_streams.extend(streams)

def _stream_snapshot():
    with _streams_lock:
        return list(all_streams)

def _stream_count():
    with _streams_lock:
        return len(all_streams)

def _publish_stream(stream, generation):
    """Publish a resolved stream only while its episode generation is current."""
    link = stream.get("link")
    with _streams_lock:
        if generation != _streams_generation:
            return False
        if link and any(existing.get("link") == link for existing in all_streams):
            return False
        all_streams.append(stream)
        return True

def _generation_is_current(generation):
    with _streams_lock:
        return generation == _streams_generation

def _update_bg_stats(generation, *, current=None, resolved=0, failed=0):
    with _bg_lock:
        if generation != _bg_generation:
            return False
        if current is not None:
            _bg_stats["current"] = current
        _bg_stats["resolved"] += resolved
        _bg_stats["failed"] += failed
        return True

def start_bg_resolve(ep_data, exclude_names: set):
    """
    Start resolving all remaining sources in background.
    Call after the first stream is already playing.
    exclude_names: source names already resolved (skip them to avoid duplicates).
    """
    global _streams_generation, _bg_thread, _bg_generation, _bg_stats
    sources = sorted(ep_data.get("episode",{}).get("sourceUrls",[]),
                     key=source_priority)
    with _streams_lock:
        _streams_generation += 1
        generation = _streams_generation
        seen_links = {s.get("link") for s in all_streams}
    with _bg_lock:
        _bg_generation = generation
        _bg_stats = {"resolved": len(exclude_names), "failed": 0, "total": len(sources), "current": ""}

    def worker():
        for src in sources:
            if not _generation_is_current(generation):
                return
            sname = src.get("sourceName","")
            if sname in exclude_names:
                continue
            if not _update_bg_stats(generation, current=sname):
                return
            try:
                found = False
                for stream in resolve_source(src, silent=True):
                    if not _generation_is_current(generation):
                        return
                    link = stream.get("link")
                    if link not in seen_links and _publish_stream(stream, generation):
                        seen_links.add(link)
                        found = True
                if not _update_bg_stats(
                    generation,
                    resolved=1 if found else 0,
                    failed=0 if found else 1
                ):
                    return
            except Exception:
                if not _update_bg_stats(generation, failed=1):
                    return
        _update_bg_stats(generation, current="")

    with _bg_lock:
        _bg_thread = threading.Thread(target=worker, daemon=True)
        _bg_thread.start()


def wait_for_bg():
    """Join bg thread if still running. Called before showing Mirrors."""
    global _bg_thread
    with _bg_lock:
        t = _bg_thread
    if t and t.is_alive():
        print(f"{YELLOW}Checking remaining mirrors...{RESET}")
        t.join()


def _redraw_player(props):
    _player_ui_state["mpv_props"] = props
    render_player_screen()


_ipc_player = MpvIpc(_redraw_player)
atexit.register(_ipc_player.quit)

def play_desktop(title, ep, stream, fetch_callback=None, total_eps=1, is_binge=False, show_id=None, osd_msg="", episode_index=0, next_episode=None):
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
    )
def play_local_video(path, player="mpv"):
    return local_playback.play_local_video(
        path,
        player,
        termux=is_termux(),
        error=err,
    )

def browse_download_library(flags, ui, cfg, args):
    base, library = scan_download_library(cfg.get("download_dir", ""))
    if not base:
        err("download_dir is not set. Add it to config before using --downloads.")
        return
    if not os.path.isdir(base):
        err(f"Download folder does not exist: {base}")
        return
    if not library:
        warn(f"No downloaded videos found in {base}.")
        return

    folder_opts = [f"{g['name']}  ({len(g['files'])})" for g in library]

    def _folders_hdr(si):
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        line = f"Downloaded anime  │  {base}  │  Enter=episodes  Esc=quit"
        return f"{_C_HINT}{_truncate_display(line, max(1, w - 1))}{_RST}"

    while True:
        folder_idx = tui_pick(
            flags, ui, "Downloads", folder_opts,
            header_fn=_folders_hdr,
            help_dict=picker_help("Open episodes", "Quit", "Quit")
        )
        if folder_idx < 0:
            return

        group = library[folder_idx]
        files = group["files"]
        file_opts = [os.path.basename(p) for p in files]

        def _files_hdr(si):
            try:
                w = os.get_terminal_size().columns
            except OSError:
                w = 80
            selected = file_opts[si] if 0 <= si < len(file_opts) else ""
            parts = [
                f"{BOLD}{_truncate_display(group['name'], max(1, w - 1))}{RESET}",
                f"{_C_HINT}{_truncate_display(selected, max(1, w - 1))}{_RST}" if selected else "",
                f"{_C_HINT}{len(files)} file(s)  │  Enter=play  Left/Esc=back{_RST}",
            ]
            return "\n".join(p for p in parts if p)

        file_idx = tui_pick(
            flags, ui, "Downloaded Episodes", file_opts,
            header_fn=_files_hdr,
            help_dict=picker_help("Play file", "Back to folders", "Back to folders")
        )
        if file_idx < 0:
            continue
        play_local_video(files[file_idx], args.player or cfg.get("player", "mpv"))


# ── Main ──────────────────────────────────────────────────────────────────────

def fetch_episode_stream(show_id, ep_number, ttype="sub", quality="best"):
    ep_data = get_episode_data(show_id, ep_number, ttype)
    if not ep_data: return None
    sources = ep_data.get("episode",{}).get("sourceUrls",[])
    pref = get_preferred_mirror(show_id)
    pref_name = pref.get("source_name", "")
    pref_res = pref.get("resolution", "")

    def dynamic_prio(src):
        api_name = src.get("sourceName", "")
        if pref_name.startswith(api_name) and api_name: return 0
        return source_priority(src)

    for src in sorted(sources, key=dynamic_prio):
        streams = resolve_source(src)
        if streams:
            selected_stream = streams[0]
            found_pref = False
            if pref_name:
                for s in streams:
                    if s.get("source_name") == pref_name and s.get("resolution", "?") == pref_res:
                        selected_stream = s
                        found_pref = True
                        break
            if not found_pref:
                for s in streams:
                    if quality in s.get("resolution","") or quality=="best":
                        selected_stream = s; break
            return selected_stream, src.get("sourceName",""), ep_data, streams
    return None

def main():
    global all_streams, _bg_thread

    args, pa = parse_cli_args()
    check_deps()
    cfg = load_config()

    globals()["DEBUG_MODE"] = args.debug
    globals()["INCOGNITO_MODE"] = bool(args.incognito)
    if args.incognito and (args.download or args.downloads or args.login or args.logout):
        pa.error("--incognito cannot be combined with downloads, login, or logout")
    if args.incognito:
        args.no_sync = True
    globals()["SYNC_FORCE_ON"] = bool(args.sync and not args.no_sync)
    globals()["SYNC_FORCE_OFF"] = bool(args.no_sync)
    globals()["SHOW_IMAGE"] = args.cover or cfg.get("cover", False)

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
                res = search_anime(q, ttype)
                print(json.dumps(res, indent=2))
        sys.exit(0)

    if args.logout:
        cfg["anilist_token"] = ""
        save_config(cfg)
        print(f"{GREEN}Logged out of AniList.{RESET}")
        sys.exit(0)

    if args.login:
        print(f"\n{YELLOW}AniList login{RESET}")
        print("Open this link, sign in, and copy the token:")
        print("\033[4mhttps://anilist.co/api/v2/oauth/authorize?client_id=9857&response_type=token\033[0m")
        tkn = prompt_anilist_token()
        if tkn:
            cfg["anilist_token"] = tkn
            save_config(cfg)
            print(f"{GREEN}AniList token saved.{RESET}")
        else:
            print(f"{RED}No token provided.{RESET}")
        sys.exit(0)

    from allmanga_cli.context import CliFlags, UiState, MachineState
    import allmanga_cli.app as handlers

    flags = CliFlags(
        debug_mode=globals().get("DEBUG_MODE", False),
        incognito_mode=globals().get("INCOGNITO_MODE", False),
        sync_force_on=globals().get("SYNC_FORCE_ON", False),
        sync_force_off=globals().get("SYNC_FORCE_OFF", False),
        show_image=globals().get("SHOW_IMAGE", False),
    )
    ui = UiState()

    def warn_before_tui(message):
        print(f"\n{YELLOW}{message}{RESET}")
        print("Continuing in 3 seconds...")
        time.sleep(3)

    if args.sync and not args.no_sync:
        if args.history or args.cont:
            warn_before_tui(
                "--sync only applies to searched titles. History and continue stay local."
            )
            args.sync = False
            globals()["SYNC_FORCE_ON"] = False
            flags.sync_force_on = False
        elif not cfg.get("anilist_token") and not args.anilist:
            warn_before_tui(
                "--sync needs AniList login. Sync is disabled for this session."
            )
            args.sync = False
            args.no_sync = True
            globals()["SYNC_FORCE_ON"] = False
            globals()["SYNC_FORCE_OFF"] = True
            flags.sync_force_on = False
            flags.sync_force_off = True

    if args.downloads:
        browse_download_library(flags, ui, cfg, args)
        sys.exit(0)

    def resolveTracking(ctx, args, cfg, show=None):
        show = show or get_ui_show(ui)

        if getattr(args, "no_sync", False):
            return False

        if getattr(args, "sync", False) and ctx == "SEARCH":
            return bool(cfg.get("anilist_token") and show and get_show_anilist_id(show))

        if ctx in ("ANILIST_BROWSE", "ANILIST_SEARCH"):
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
            cfg["anilist_token"] = tkn
            save_config(cfg)
            print(f"{GREEN}AniList token saved.{RESET}")
        else:
            print(f"{RED}No token provided. Tracking is disabled for this session.{RESET}")
            args.no_sync = True
            globals()["SYNC_FORCE_ON"] = False
            globals()["SYNC_FORCE_OFF"] = True
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
    quality = args.quality or cfg.get("quality","1080p")

    ms = MachineState(
        query_str=" ".join(args.query) if args.query else "",
        just_searched=bool(args.query),
        anilist_search_parent="QUIT"
    )

    state = "SEARCH"

    if args.anilist is not None:
        if args.anilist == "search":
            state = "ANILIST_SEARCH"
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
            prepare_show_display_state(flags, show, h.get("translation_type", ttype))
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
    elif args.history:
        state = "HISTORY"

    while state != "QUIT":
        if state == "SEARCH":
            state = handlers.handle_search_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "HISTORY":
            state = handlers.handle_history_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "ANILIST_MENU":
            state = handlers.handle_anilist_menu_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "ANILIST_BROWSE":
            state = handlers.handle_anilist_browse_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "ANILIST_SEARCH":
            state = handlers.handle_anilist_search_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "DETAILS":
            state = handlers.handle_details_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "UPDATE_PROGRESS":
            state = handlers.handle_update_progress_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "UPDATE_STATUS":
            state = handlers.handle_update_status_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "UPDATE_SCORE":
            state = handlers.handle_update_score_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "EPISODE":
            state = handlers.handle_episode_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "PLAY":
            state = handlers.handle_play_state(flags, ui, ms, cfg, args, ttype, quality, resolveTracking)
        elif state == "ACTION_MENU":
            state = handlers.handle_action_menu_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        elif state == "MIRRORS":
            state = handlers.handle_mirrors_state(flags, ui, ms, cfg, args, ttype, resolveTracking)
        else:
            err(f"Unknown state: {state}")
            state = "QUIT"

    _ipc_player.quit()
