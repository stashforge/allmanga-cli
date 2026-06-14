#!/usr/bin/env python3
"""
allmanga-cli — Terminal anime stream player (AllAnime / AllManga)
"""

import sys, shutil, threading, os, re, json, time
import hashlib, subprocess
import tty, termios, select, signal, atexit, tempfile, getpass, traceback
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
    return bool(globals().get("INCOGNITO_MODE", False))

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
    if globals().get("DEBUG_MODE", False):
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

def set_ui_context(show, ttype):
    globals()["_ui_show_ctx"] = show
    globals()["_ui_ttype_ctx"] = ttype

def get_ui_show(default=None):
    if default is None:
        default = {}
    return globals().get("_ui_show_ctx", default)

def get_ui_ttype(default="sub"):
    return globals().get("_ui_ttype_ctx", default)

def set_navigation_context(search_prev=None, ep_prev=None, action_prev=None):
    if search_prev is not None:
        globals()["_search_prev_state"] = search_prev
    if ep_prev is not None:
        globals()["_ep_prev_state"] = ep_prev
    if action_prev is not None:
        globals()["_action_prev_state"] = action_prev

def get_search_prev(default="SEARCH"):
    return globals().get("_search_prev_state", default)

def get_ep_prev(default="SEARCH"):
    return globals().get("_ep_prev_state", default)

def get_action_prev(default="SEARCH"):
    return globals().get("_action_prev_state", default)

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

def buildInfoMetadataLine(show, ttype, override_ep_str=None):
    return format_info_metadata_line(show, ttype, override_ep_str=override_ep_str)

def sync_progress_and_checkpoint(token, title, progress, media_id, show, ttype, status=None):
    status = tracking_status_for_progress(show, progress) if status is None else status
    progress = tracking_progress_for_sync(show, progress, status)
    if not scrobble_anilist(token, title, progress, media_id=media_id, status=status):
        return False
    apply_tracking_progress_local(show, progress, status)
    set_last_synced_progress(show, progress, ttype)
    show["_progress_authority"] = "AL"
    return True

def sync_watched_to_anilist(token, title, ep, media_id, show):
    return sync_progress_and_checkpoint(
        token, title, ep, media_id, show, get_ui_ttype()
    )

def save_and_sync_watched(show, episode, ttype, token, title, progress, media_id):
    save_history(show, episode, ttype)
    return sync_watched_to_anilist(token, title, progress, media_id, show)

def set_action_feedback(show, msg):
    show["_action_feedback"] = msg
    show["_action_feedback_time"] = time.time()

def build_info_panel(show, ttype, w, parts, override_ep_str=None, main_title=None):
    C_T  = "\033[1;97m"
    C_D  = "\033[38;5;248m"
    R    = "\033[0m"

    prepare_show_display_state(show, ttype, show.get("_sync_enabled") if "_sync_enabled" in show else None)
    title = main_title if main_title else get_show_display_title(show)
    alt = get_display_titles(show, title)

    _t = lambda s: _truncate_display(s, max(1, w - 1))
    info_title_line = f"{C_T}{_t(title)}{R}"
    info_alt_title_line = f"{C_D}{_t(alt)}{R}" if alt else f"{C_D}No alternative title{R}"

    metadata = buildInfoMetadataLine(show, ttype, override_ep_str)
    if is_incognito():
        info_metadata_line = f"{_t(f'{YELLOW}INCOGNITO{C_D} • {metadata}')}{R}"
    else:
        info_metadata_line = f"{C_D}{_t(metadata)}{R}"

    parts.extend([info_title_line, info_alt_title_line, info_metadata_line])


def _request_poster_redraw():
    global _needs_redraw
    _needs_redraw = True


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

def tui_pick(prompt, options, header="", hints=None, live_fn=None, header_fn=None, top_header_fn=None, tab_fn=None, delete_fn=None, right_fn=None, return_query_on_enter=False, query_history=None, hide_separator=False, initial_query="", is_search=False, help_dict=None, auto_select_single_when_done=False, keep_cursor_hidden_on_select=False, count_total=None):
    """
    Bottom-anchored alt-screen picker with flipped (bottom-up) item list.
    Returns index, -2 (Esc), -3 (Left).

    live_fn:   optional callable(query) -> (new_options, new_header, done)
    header_fn: optional callable(sel_index) -> header_str
               Called each render to build header based on current selection.
    """
    def current_prompt():
        return str(prompt() if callable(prompt) else prompt)

    def fallback_pick():
        return fallback_tui_pick(
            current_prompt(),
            options,
            return_query_on_enter=return_query_on_enter,
            initial_query=initial_query,
        )

    tty_fd = -1
    tty_file = None
    try:
        tty_fd = os.open("/dev/tty", os.O_RDWR)
        tty_file = os.fdopen(tty_fd, "rb+", buffering=0)
        tty_fd = tty_file.fileno()
    except OSError:
        if tty_file:
            try:
                tty_file.close()
            except Exception:
                pass
            tty_file = None
        if tty_fd >= 0:
            os.close(tty_fd)
        return fallback_pick()

    try:
        old_attrs = termios.tcgetattr(tty_fd)
    except Exception:
        try:
            tty_file.close()
        except Exception:
            pass
        return fallback_pick()
    enter_alt_screen()
    query  = initial_query
    cursor_pos = len(query)
    sel    = 0
    scroll = 0
    history_idx = -1
    cur_header = header_fn(0) if header_fn else header
    show_help = False
    last_poster_tick = 0
    last_poster_key = None
    last_clock_minute = int(time.time() // 60)

    def filt_list():
        if not query:
            return list(range(len(options)))
        return [i for i, o in enumerate(options)
                if _match(query, _strip_ansi(o)) is not None]

    def render(filt):
        nonlocal scroll, last_poster_key
        try:
            sz = os.get_terminal_size(tty_fd)
            rows, cols = sz.lines, sz.columns
        except OSError:
            rows, cols = 24, 80

        if show_help and help_dict:
            out = []
            out.append("\033[2K")
            out.append(f"\033[2K  {_C_HINT}=== Keyboard Shortcuts ==={_RST}")
            out.append("\033[2K")
            for k, v in help_dict.items():
                out.append(f"\033[2K  {_C_PTR}{k:<15}{_RST} {v}")
            out.append("\033[2K")
            out.append(f"\033[2K  {_C_HINT}Press Esc or ? to close{_RST}")

            padding = rows - len(out)
            for _ in range(padding):
                out.append("\033[2K")

            buf = _absolute_terminal_frame(out, rows, cols)
            tty_file.write(buf.encode())
            tty_file.flush()
            return

        actual_top_header = None
        if top_header_fn is not None and filt:
            sel_idx = filt[sel] if sel < len(filt) else -1
            actual_top_header = top_header_fn(sel_idx)

        actual_header = cur_header
        if header_fn is not None:
            sel_idx = filt[sel] if (filt and sel < len(filt)) else -1
            globals()["_active_picker_query"] = query
            actual_header = header_fn(sel_idx)
        header_lines = actual_header.splitlines() if actual_header else []
        header_n = max(4, len(header_lines)) if header_fn is not None else len(header_lines)

        show_img = globals().get("SHOW_IMAGE", False)

        is_tmx = (os.environ.get("PREFIX","").startswith("/data/data/com.termux") or os.path.exists("/data/data/com.termux"))
        top_header_n = (9 if is_tmx else 8) if (show_img and top_header_fn is not None) else 0
        top_margin = 1 if top_header_n > 0 else 0

        # Fixed zones: prompt line (1) + header_n + poster + poster margin
        GAP = 0
        fixed = top_margin + 1 + header_n + top_header_n + GAP

        # If viewport < 10 rows: hide poster, recalculate
        if rows - fixed < 10 and top_header_n > 0:
            top_header_n = 0
            top_margin = 0
            GAP = 0
            fixed = 1 + header_n

        max_vis, _, _ = _picker_vertical_layout(
            rows, header_n, top_header_n, top_margin, GAP, len(filt)
        )

        if filt:
            if sel < scroll:
                scroll = sel
            elif sel >= scroll + max_vis:
                scroll = sel - max_vis + 1

        out = []

        # --- Items (bottom-up: index 0 at the bottom) ---
        visible = filt[scroll:scroll + max_vis] if filt else []
        items_shown = len(visible)
        item_max_w = max(20, cols - 3)

        # --- Padding (empty space) ---
        # In a bottom-anchored layout, the padding goes at the absolute TOP of the screen
        # This pushes the entire UI block down to the bottom.
        _, _, padding = _picker_vertical_layout(
            rows, header_n, top_header_n, top_margin, GAP, items_shown
        )

        for _ in range(padding):
            out.append("\033[2K")

        poster_key = None
        native_poster = ""
        poster_row = None

        # --- Top: fixed image container ---
        if top_header_n > 0:
            poster_raw = actual_top_header or ""
            poster_lines = _poster_symbol_lines(poster_raw, top_header_n, cols)
            poster_row = len(out) + 1
            poster_key = (
                globals().get("_hovered_show_id"),
                hashlib.sha256(poster_raw.encode("utf-8", errors="ignore")).hexdigest(),
                poster_row,
                top_header_n,
                cols,
            )
            native_poster = poster_raw if _poster_uses_native_protocol(poster_raw) else ""
            for row in range(top_header_n):
                line = poster_lines[row] if row < len(poster_lines) else ""
                out.append(f"\033[2K{line}")

        # --- Fixed gap between image and items ---
        for _ in range(top_margin):
            out.append("\033[2K")
        for _ in range(GAP):
            out.append("\033[2K")

        for vi in range(items_shown - 1, -1, -1):
            oi = visible[vi]
            is_sel = (scroll + vi == sel)
            ptr   = f"{_C_PTR}\u276f{_RST}" if is_sel else " "
            label = _render_item(options[oi], query, is_sel, max_w=item_max_w)
            hint  = ""
            if is_sel and hints:
                kp = _strip_ansi(options[oi])
                for k, v in hints.items():
                    if _strip_ansi(k) == kp:
                        hint_text = str(v)
                        if hint_text.strip().lower() != kp.strip().lower():
                            hint_w = max(0, cols - _display_width(ptr) - 2 - _display_width(label) - 2)
                        else:
                            hint_w = 0
                        if hint_w > 0:
                            hint = f"  {_C_HINT}{_truncate_display(hint_text, hint_w)}{_RST}"
                        break
            out.append(f"\033[2K{_fit_terminal_line(f'{ptr} {label}{hint}', cols)}")

        # --- Prompt + count + separator ---
        if is_search:
            q_left = query[:cursor_pos]
            q_char = query[cursor_pos] if cursor_pos < len(query) else " "
            q_right = query[cursor_pos+1:]
            styled_query = f"{q_left}\033[7m{q_char}\033[27m{q_right}"
            pstr = f"{_C_PROMPT}{current_prompt()} \u276f{_RST} {_C_QUERY}{styled_query}{_RST}"
        else:
            pstr = f"{_C_PROMPT}{current_prompt()} \u276f{_RST} {_C_QUERY}{query}{_RST}"

        if hide_separator or len(options) == 0:
            out.append(f"\033[2K{_fit_terminal_line(pstr, cols)}")
        else:
            total_count = count_total() if callable(count_total) else count_total
            total_count = len(options) if total_count is None else total_count
            cstr = f"{_C_COUNT}{len(filt)}/{total_count}{_RST}"
            hidden_below = scroll
            hidden_above = max(0, len(filt) - scroll - max_vis)
            si = ""
            if hidden_above > 0: si += f"\u25b2{hidden_above} "
            if hidden_below > 0: si += f"\u25bc{hidden_below} "
            if si: si = f" {_C_SCROLLI}{si}{_RST}"

            left_str = f"{pstr}  {cstr}{si}"
            used = _display_width(left_str)
            sep_w = max(1, cols - used - 2)
            sep = f" {_C_HINT}{'\u2500' * sep_w}{_RST}"
            out.append(f"\033[2K{_fit_terminal_line(f'{pstr}  {cstr}{si}{sep}', cols)}")

        # --- Bottom: info panel (strictly padded to header_n) ---
        for line in _bottom_align_panel_lines(header_lines, header_n):
            if not line:
                out.append("\033[2K")
            else:
                out.append(f"\033[2K{_fit_terminal_line(line, cols)}")

        # --- Draw: repaint from row 1 and clear only leftover lines below the UI. ---
        # Clear old native graphics only when the selected cover changes.
        poster_changed = poster_key != last_poster_key
        clear_prefix = (
            _clear_terminal_images() + "\033[2J"
            if poster_changed and (poster_key is not None or last_poster_key is not None)
            else ""
        )
        last_poster_key = poster_key
        overlay = ""
        if poster_changed and native_poster and poster_row is not None:
            overlay = f"\033[{poster_row};1H{native_poster}"
        frame = _absolute_terminal_frame(out, rows, cols)
        buf = (
            f"{clear_prefix}\033[?25l"
            + frame
            + overlay
            + "\033[1;1H\033[?25l"
        )
        tty_file.write(buf.encode())
        tty_file.flush()

    try:
        tty_file.write(b"\033[2J\033[?25l")
        tty_file.flush()
        tty.setraw(tty_fd)
        termios.tcflush(tty_fd, termios.TCIFLUSH)

        filt   = filt_list()
        result = -2

        if live_fn is None and len(options) == 0 and not return_query_on_enter and tab_fn is None:
            result = -4
            return result

        global _needs_redraw
        _needs_redraw = True

        while True:
            clock_minute = int(time.time() // 60)
            if clock_minute != last_clock_minute:
                last_clock_minute = clock_minute
                _needs_redraw = True

            # Live refresh
            if live_fn is not None:
                new_opts, new_hdr, _done = live_fn(query)
                if new_opts != options:
                    options.clear()
                    options.extend(new_opts)
                    filt = filt_list()
                    _needs_redraw = True
                if cur_header != new_hdr:
                    cur_header = new_hdr
                    _needs_redraw = True

                if _done and auto_select_single_when_done and len(options) == 1:
                    result = 0
                    break

                if _done and len(options) == 0:
                    result = -4
                    break

            sel = max(0, min(sel, len(filt) - 1)) if filt else 0

            if globals().get("SHOW_IMAGE", False) and top_header_fn is not None and filt:
                now = time.time()
                sel_idx = filt[sel] if sel < len(filt) else -1
                if 0 <= sel_idx < len(options):
                    show_obj = globals().get("_hovered_show_obj")
                    if _poster_needs_tick(show_obj) and now - last_poster_tick >= 0.5:
                        last_poster_tick = now
                        _needs_redraw = True

            if _needs_redraw:
                render(filt)
                _needs_redraw = False

            # Use a small timeout (50ms) to process SIGWINCH async flags instantly without burning CPU
            try:
                ready = select.select([tty_fd], [], [], 0.05)[0]
            except InterruptedError:
                continue

            if not ready:
                continue

            key = _get_key(tty_fd)
            termios.tcflush(tty_fd, termios.TCIFLUSH)
            _needs_redraw = True

            if key == "UP":
                if filt:
                    sel = (sel + 1) % len(filt)
                elif query_history:
                    history_idx = min(history_idx + 1, len(query_history) - 1)
                    if history_idx >= 0:
                        query = query_history[history_idx]
                        cursor_pos = len(query)
                        filt = filt_list()
            elif key == "DOWN":
                if filt:
                    sel = (sel - 1) % len(filt)
                elif query_history:
                    history_idx = max(history_idx - 1, -1)
                    if history_idx >= 0:
                        query = query_history[history_idx]
                    else:
                        query = ""
                    cursor_pos = len(query)
                    filt = filt_list()
            elif key == "HOME":
                sel = 0; scroll = 0
            elif key == "END":
                sel = max(0, len(filt) - 1)
            elif key in ("ENTER", "RIGHT"):
                if is_search and key == "RIGHT":
                    if cursor_pos < len(query): cursor_pos += 1
                    _needs_redraw = True
                    continue
                if return_query_on_enter:
                    result = query
                    break
                if filt: result = filt[sel]
                break
            elif key == "?" and help_dict:
                show_help = not show_help
            elif key == "ESC":
                if show_help:
                    show_help = False
                else:
                    result = -2; break
            elif key == "CTRL_C":
                raise KeyboardInterrupt
            elif key == "LEFT":
                if is_search:
                    if cursor_pos > 0: cursor_pos -= 1
                    _needs_redraw = True
                else:
                    result = -3; break
            elif key == "BACKSPACE":
                if is_search:
                    if cursor_pos > 0:
                        query = query[:cursor_pos-1] + query[cursor_pos:]
                        cursor_pos -= 1
                        filt = filt_list(); sel = 0; scroll = 0
                else:
                    query = query[:-1]; filt = filt_list(); sel = 0; scroll = 0
                    cursor_pos = len(query)
            elif key == "CTRL_U":
                query = "";         filt = filt_list(); sel = 0; scroll = 0
                cursor_pos = 0
            elif key == "TAB":
                if tab_fn:
                    selected = filt[sel] if filt and sel < len(filt) else None
                    res = tab_fn(selected)
                    if res:
                        options, cur_header = res[0], res[1]
                        filt = filt_list()
                        sel = max(0, min(sel, len(filt) - 1)) if filt else 0
            elif key == "DELETE":
                if delete_fn and filt:
                    res = delete_fn(filt[sel])
                    if res:
                        options, cur_header = res[0], res[1]
                        filt = filt_list()
                        sel = max(0, min(sel, len(filt) - 1)) if filt else 0
            elif key not in ("SHIFT_TAB", "UNKNOWN"):
                if len(key) == 1 and key.isprintable():
                    if is_search:
                        query = query[:cursor_pos] + key + query[cursor_pos:]
                        cursor_pos += 1
                    else:
                        query += key
                        cursor_pos = len(query)
                    filt = filt_list(); sel = 0; scroll = 0

    finally:
        termios.tcsetattr(tty_fd, termios.TCSADRAIN, old_attrs)
        # We rely on the global atexit and __main__ finally block to restore the cursor
        # to prevent cursor flickering during rapid screen transitions.
        tty_file.flush()
        try:
            tty_file.close()
        except Exception:
            pass

    return result

# ── Watch history & State ─────────────────────────────────────────────────────
_prefs_cache = None  # in-memory cache for playback prefs

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
    if not show:
        return None
    show_id = str(show.get("_id") or "")
    if not show_id:
        return None
    for entry in load_history():
        entry_show = entry.get("show", {})
        if (str(entry_show.get("_id") or "") == show_id
                and entry.get("translation_type", "sub") == ttype):
            episode_id = entry.get("episode", 0)
            if str(episode_id) in ("0", "0.0"):
                return 0
            episode_ids = show.get("_episode_ids") or entry_show.get("_episode_ids") or []
            if episode_ids:
                episode_index = episode_index_for_id(
                    [str(ep) for ep in episode_ids], episode_id
                )
                return episode_index + 1 if episode_index is not None else None
            try:
                return max(0, int(float(str(episode_id))))
            except (TypeError, ValueError):
                return None
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
    try:
        progress = max(0, int(progress))
    except (TypeError, ValueError):
        progress = 0
    if progress == 0:
        return "0"
    episode_ids = ensure_episode_ids(show, ttype)
    if episode_ids and progress <= len(episode_ids):
        return episode_id_at(episode_ids, progress - 1)
    if show.get("_id"):
        return None
    return str(progress)

def write_history_progress(show, progress, ttype, *, last_synced=None, touch=False):
    global _history_cache
    if is_incognito():
        return None
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        progress = max(0, int(progress))
    except (TypeError, ValueError):
        progress = 0
    history = load_history()
    old = get_history_entry(show, ttype)
    timestamp = int(time.time()) if touch else int((old or {}).get("timestamp") or time.time())
    stored_show = dict(show)
    for key in ("_anilist_context", "_progress_authority", "_sync_conflict"):
        stored_show.pop(key, None)
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
    _atomic_write_json(HISTORY_PATH, history, indent=2)
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
        and not show.get("_anilist_id")
    )
    if raw_anilist_show:
        show["_anilist_id"] = show.get("_id")
    if globals().get("SYNC_FORCE_OFF", False):
        sync_enabled = False
    elif sync_enabled is None and raw_anilist_show:
        sync_enabled = True
    elif sync_enabled is None and globals().get("SYNC_FORCE_ON", False) and show.get("_anilist_id"):
        sync_enabled = True
    elif sync_enabled is None:
        sync_enabled = get_title_sync(show)
    show["_sync_enabled"] = bool(sync_enabled)
    show["_local_progress"] = get_local_progress(show, ttype)
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
    show_id = show.get("_id")
    history_ep = h.get("episode", 1)
    tt = ttype or h.get("translation_type", "sub")
    episode_ids = ensure_episode_ids(show, tt)
    if episode_ids:
        if str(history_ep) in ("0", "0.0"):
            return episode_id_at(episode_ids, 0)
        history_index = episode_index_for_id(episode_ids, history_ep)
        if history_index is None:
            return None
        if show_id and get_resume_time(show_id, history_ep) > 0:
            return episode_id_at(episode_ids, history_index)
        return episode_id_at(episode_ids, min(history_index + 1, len(episode_ids) - 1))

    try:
        history_ep = max(1, int(float(str(history_ep))))
    except (TypeError, ValueError):
        history_ep = 1
    total_eps = show.get("availableEpisodes", {}).get(tt, 0)
    try:
        total_eps = int(total_eps) if total_eps else 0
    except (TypeError, ValueError):
        total_eps = 0

    if show_id and get_resume_time(show_id, history_ep) > 0:
        return min(history_ep, total_eps) if total_eps else history_ep

    next_ep = history_ep + 1
    return min(next_ep, total_eps) if total_eps else next_ep

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
    if _history_cache is not None:
        return _history_cache
    if not os.path.exists(HISTORY_PATH): return []
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _history_cache = data if isinstance(data, list) else []
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
        progress = episode_index + 1
    else:
        progress = episode_progress_number(episode)
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
    history = load_history()
    before = len(history)
    history = [
        h for h in history
        if not (str(h.get("show", {}).get("_id")) == str(show_id)
                and h.get("translation_type") == ttype)
    ]
    if len(history) == before:
        return False
    try:
        _atomic_write_json(HISTORY_PATH, history, indent=2)
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

def get_anilist_media_id(anime):
    return anilist_service.media_id(anime)

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

def save_refreshed_history(history):
    global _history_cache
    if is_incognito():
        return False
    try:
        _atomic_write_json(HISTORY_PATH, history, indent=2)
        _history_cache = history
        return True
    except Exception as e:
        debug_warn("Failed to save refreshed history", e)
        return False

def refresh_expired_history_airing(history, token):
    if not token:
        return history
    changed = False
    now = int(time.time())
    for h in history:
        show = h.get("show", {})
        al_id = get_anilist_media_id(show)
        if not al_id or not should_refresh_anilist(show, now):
            continue
        media = fetch_anilist_media(token, al_id)
        if not media:
            continue
        changed = update_anime_from_anilist_media(show, media) or changed
    if changed:
        save_refreshed_history(history)
    return history

def load_search_history():
    global _search_history_cache
    if _search_history_cache is not None:
        return _search_history_cache
    if not os.path.exists(SEARCH_HISTORY_PATH):
        _search_history_cache = []
        return _search_history_cache
    try:
        with open(SEARCH_HISTORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _search_history_cache = data if isinstance(data, list) else []
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
    if not query: return
    os.makedirs(STATE_DIR, exist_ok=True)
    history = load_search_history()
    if query in history: history.remove(query)
    history.insert(0, query)
    history = history[:HISTORY_MAX]
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

def history_entry_progress(entry):
    return history_domain.history_entry_progress(
        entry,
        prepare_display_state=prepare_show_display_state,
        get_local_progress=get_local_progress,
    )

def history_entry_is_completed(entry):
    return history_domain.history_entry_is_completed(
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
def scrobble_anilist(token, title, ep, media_id=None, status=None):
    try:
        if media_id is None:
            media_id = anilist_service.search_media_id(
                anilist_urlopen,
                read_json_response,
                title,
            )

        return update_anilist_entry(token, int(media_id), progress=ep, status=status)
    except Exception:
        return False

def update_anilist_entry(token, media_id, progress=None, status=None, score=None):
    if is_incognito():
        return False
    try:
        res = anilist_service.update_entry(
            anilist_urlopen,
            read_json_response,
            token,
            media_id,
            progress=progress,
            status=status,
            score=score,
        )
        if res.get("errors"):
            debug_warn("AniList update returned errors", res.get("errors"))
            return False
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
        if _anilist_queue_cache is not None:
            return _anilist_queue_cache
        if not os.path.exists(ANILIST_QUEUE_PATH):
            _anilist_queue_cache = []
            return _anilist_queue_cache
        try:
            with open(ANILIST_QUEUE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _anilist_queue_cache = data if isinstance(data, list) else []
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
        try:
            os.chmod(ANILIST_QUEUE_PATH, 0o600)
        except OSError:
            pass
        _anilist_queue_cache = records
        return True

def _anilist_mutation_key(record):
    return anilist_queue_state.mutation_key(record)

def _enqueue_anilist_progress(media_id, title, progress, status, show, ttype,
                              pending_completion=None):
    record = anilist_queue_state.make_progress_record(
        media_id,
        title,
        progress,
        status,
        show,
        ttype,
        pending_completion,
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
    global _history_cache
    show_id = str(record.get("show_id") or "")
    if not show_id:
        return
    progress = max(0, int(record.get("progress") or 0))
    ttype = record.get("ttype") or "sub"
    history = load_history()
    changed = False
    for entry in history:
        stored_show = entry.get("show", {})
        if (str(stored_show.get("_id") or "") == show_id
                and entry.get("translation_type", "sub") == ttype):
            entry["last_synced_progress"] = progress
            stored_show["_anilist_progress"] = progress
            if record.get("status"):
                stored_show["_anilist_list"] = record["status"]
            changed = True
            break
    if changed:
        _atomic_write_json(HISTORY_PATH, history, indent=2)
        _history_cache = history

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
        success = scrobble_anilist(
            token,
            record.get("title") or "",
            int(record["progress"]),
            media_id=record.get("media_id"),
            status=record.get("status"),
        )
        if success:
            if show is not None:
                apply_tracking_progress_local(
                    show, int(record["progress"]), record.get("status")
                )
                set_last_synced_progress(show, int(record["progress"]), record.get("ttype") or "sub")
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
    try:
        record = _enqueue_anilist_progress(
            media_id, title, progress, status, show, ttype,
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
    status = str(show.get("_anilist_list") or "").upper()
    total = _positive_int(show.get("episodeCount"))
    if not total:
        total = len(show.get("_episode_ids") or []) or None
    if total and progress >= total:
        return "COMPLETED"
    if status in ("COMPLETED", "REPEATING", "REWATCHING"):
        return "REPEATING"
    if status not in ("CURRENT", "WATCHING"):
        return "CURRENT"
    return None

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
    al_id = show.get("_anilist_id")
    if not token or not al_id:
        return {"action": "failed", "progress": progress}
    status = _reconcile_status(show, progress)
    if not update_anilist_entry(
        token,
        int(al_id),
        progress=int(progress),
        status=status,
    ):
        return {"action": "failed", "progress": progress}
    apply_tracking_progress_local(show, int(progress), status)
    write_history_progress(
        show, int(progress), ttype,
        last_synced=int(progress),
        touch=False,
    )
    show["_progress_authority"] = "AL"
    show.pop("_sync_conflict", None)
    return {"action": "pushed", "progress": int(progress), "status": status}

def reconcile_progress(show, ttype, token, *, anilist_source=False, sync_enabled=True):
    local = get_local_progress(show, ttype)
    try:
        remote = max(0, int(show.get("_anilist_progress") or 0))
    except (TypeError, ValueError):
        remote = 0
    last = get_last_synced_progress(show, ttype)
    status = str(show.get("_anilist_list") or "").upper()
    show.pop("_sync_conflict", None)

    if anilist_source and not sync_enabled:
        if local is None or last is None or local == last:
            return _import_anilist_progress(show, ttype, remote, authority="AL")
        show["_local_progress"] = local
        show["_progress_authority"] = "LOCAL"
        return {"action": "local", "progress": local}

    if anilist_source and last is None:
        return _import_anilist_progress(show, ttype, remote)

    if not sync_enabled:
        show["_local_progress"] = local
        show["_progress_authority"] = "LOCAL"
        return {"action": "local", "progress": local or 0}

    if local is None:
        return _import_anilist_progress(show, ttype, remote)
    if local == remote:
        set_last_synced_progress(show, local, ttype)
        show["_progress_authority"] = "AL"
        return {"action": "equal", "progress": local}

    if last is not None:
        local_changed = local != last
        remote_changed = remote != last
        if local_changed and remote_changed and status in ("COMPLETED", "REPEATING", "REWATCHING"):
            conflict = {"local": local, "anilist": remote}
            show["_sync_conflict"] = conflict
            show["_progress_authority"] = "LOCAL"
            return {"action": "conflict", **conflict}
        if local_changed and not remote_changed:
            return _push_local_progress(show, ttype, token, local)
        if remote_changed and not local_changed:
            return _import_anilist_progress(show, ttype, remote)

    if status == "COMPLETED" and local < remote:
        return _push_local_progress(show, ttype, token, local)
    if local > remote:
        return _push_local_progress(show, ttype, token, local)
    return _import_anilist_progress(show, ttype, remote)

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

def _run_manual_match_search(anilist_show, ttype):
    al_title = anilist_show.get("name") or anilist_show.get("englishName") or ""
    al_id = str(anilist_show.get("_id") or "")
    query = al_title
    search_error = ""
    while True:
        query = tui_pick(
            "Match AllAnime",
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
            "Match AllAnime",
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
            if al_id:
                save_al_match(al_id, chosen)
            return _merge_anilist_into_allanime(chosen, anilist_show)

def _run_manual_anilist_match(allanime_show, token):
    source_title = allanime_show.get("_allanime_name") or allanime_show.get("name") or ""
    query = source_title
    search_error = ""
    while True:
        query = tui_pick(
            "Match AniList",
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
            "Match AniList",
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
            save_source_anilist_match(allanime_show, chosen)
            return _merge_anilist_into_allanime(allanime_show, chosen)

def match_allanime_show_to_anilist(allanime_show, token, manual_on_fail=False):
    stored = get_source_anilist_match(allanime_show.get("_id"))
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
        stored_id = str(stored.get("_id") or "")
        matched = next(
            (show for show in results if str(show.get("_id") or "") == stored_id),
            None,
        ) if stored_id else None
        if not matched:
            matched = _choose_confident_match(allanime_show, results)
        if matched:
            save_source_anilist_match(allanime_show, matched)
            return _merge_anilist_into_allanime(allanime_show, matched)
    if manual_on_fail:
        return _run_manual_anilist_match(allanime_show, token)
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
    allanime_show["_anilist_id"] = anilist_show.get("_id")
    if anilist_show.get("_next_airing_ep"):
        allanime_show["_next_airing_ep"] = anilist_show["_next_airing_ep"]
        allanime_show["_next_airing_time"] = anilist_show["_next_airing_time"]
        allanime_show["_next_airing_at"] = anilist_show.get("_next_airing_at")
    if not allanime_show.get("thumbnail") and anilist_show.get("thumbnail"):
        allanime_show["thumbnail"] = anilist_show["thumbnail"]
    return allanime_show

def match_anilist_show_to_allanime(anilist_show, ttype):
    al_id = str(anilist_show.get("_id") or "")
    if al_id:
        stored = get_al_match(al_id)
        if stored.get("_id"):
            direct = get_allanime_show(stored["_id"])
            if direct:
                return _merge_anilist_into_allanime(direct, anilist_show)
            aa_shows = search_anime(stored.get("name") or anilist_show["name"], ttype)
            fallback = next((aa for aa in aa_shows if aa.get("_id") == stored["_id"]), None)
            if fallback:
                return _merge_anilist_into_allanime(fallback, anilist_show)

    aa_shows = search_anime(anilist_show["name"], ttype)
    if not aa_shows:
        aa_shows = search_anime(anilist_show.get("englishName", anilist_show["name"]), ttype)
    matched = _best_allanime_match(anilist_show, aa_shows)
    return _merge_anilist_into_allanime(matched, anilist_show) if matched else None

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
        show["_episode_ids"] = cached_ids
        return cached_ids

    legacy_ids = cached_ids
    if legacy_ids and not cached_state:
        cached_state = (
            "legacy_contiguous"
            if _is_contiguous_legacy_catalog(legacy_ids)
            else "loaded"
        )
        if cached_state == "loaded":
            show["_episode_ids"] = legacy_ids
            show["_episode_catalog_state"] = "loaded"
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
        show["_episode_ids"] = catalog["ids"]
        show["_episode_ids_ttype"] = ttype
        show["_episode_catalog_state"] = "loaded"
        show.pop("_episode_catalog_error", None)
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

def browse_download_library(cfg, args):
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
            "Downloads", folder_opts,
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
            "Downloaded Episodes", file_opts,
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

    if args.downloads:
        browse_download_library(cfg, args)
        sys.exit(0)

    def resolveTracking(ctx, args, cfg, show=None):
        show = show or get_ui_show()
        if getattr(args, "no_sync", False):
            if show and show.get("_anilist_id"):
                set_title_sync(show, False)
            return False
        if getattr(args, "sync", False):
            if show and show.get("_anilist_id"):
                set_title_sync(show, True)
            return True
        title_pref = get_title_sync_preference(show)
        if title_pref is not None:
            return title_pref
        if ctx in ("ANILIST_BROWSE", "ANILIST_SEARCH"):
            if show and show.get("_anilist_id"):
                set_title_sync(show, True)
            return True
        return cfg.get("auto_track", False)

    globals()["resolveTracking"] = resolveTracking

    # We will evaluate tracking dynamically, but we still need to prompt for token if tracking is requested anywhere
    if (cfg.get("auto_track", False) or args.sync or args.anilist) and not args.no_sync and not cfg.get("anilist_token"):
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
    if cfg.get("anilist_token") and not args.no_sync:
        retry_queued_anilist_writes(cfg["anilist_token"])
    globals()["SHOW_IMAGE"] = args.cover or cfg.get("cover", False)

    if args.episode and "-" in args.episode:
        _s, _e = args.episode.split("-")
        args.episode = _s.strip()
        globals()["_download_batch_end"] = int(_e)
    elif args.episode:
        args.episode = str(args.episode).strip()

    termux  = is_termux()
    ttype   = "dub" if (args.dub or cfg.get("translation_type")=="dub") else "sub"
    quality = args.quality or cfg.get("quality","1080p")

    query_str       = " ".join(args.query) if args.query else ""
    pending_osd_msg = ""
    just_searched   = bool(query_str)
    just_picked_anime = False
    shows           = []
    show_id         = show_title = None
    total_eps       = 0
    current_ep      = 1
    current_ep_index = 0
    selected_stream = None
    _ep_cache_key   = None
    _ep_cache_data  = None
    _last_header_key = None
    anilist_search_parent = "QUIT"

    state           = "SEARCH"

    if args.anilist is not None:
        if args.anilist == "search":
            state = "ANILIST_SEARCH"
        else:
            if not cfg.get("anilist_token"):
                print(f"\n{YELLOW}AniList account is not linked.{RESET}")
                print(f"Run {BOLD}./allmanga-cli --login{RESET} to authenticate.")
                sys.exit(1)
            state = "ANILIST_MENU"
    # ── Handle --continue: resume last watched ──────────────────────────────
    elif args.cont:
        hist = load_history()
        if hist:
            h = hist[0]
            show = h.get("show", {})
            prepare_show_display_state(show, h.get("translation_type", ttype))
            show_id    = show.get("_id")
            show_title = get_show_display_title(show)
            ttype      = h.get("translation_type", ttype)
            total_eps  = show.get("availableEpisodes", {}).get(ttype, 1)
            current_ep = playback_ep_from_history_entry(h, ttype)
            episode_ids = ensure_episode_ids(show, ttype)
            total_eps = len(episode_ids) or total_eps
            current_ep_index = episode_index_for_id(episode_ids, current_ep)
            set_ui_context(show, ttype)
            if not episode_ids:
                err(episode_catalog_error(show))
                state = "HISTORY"
            elif current_ep_index is None:
                err("Saved episode is not present in the current provider catalog.")
                state = "HISTORY"
            else:
                current_ep = episode_id_at(episode_ids, current_ep_index)
                info(f"Continuing {show_title}: EP {current_ep}/{total_eps}")
                state = "PLAY"
        else:
            warn("Watch history is empty.")

    # ── Handle --history: browse history ──────────────────────────────────
    elif args.history:
        state = "HISTORY"

    while state != "QUIT":

        # ── HISTORY ───────────────────────────────────────────────────────
        if state == "HISTORY":
            hist = refresh_expired_history_airing(load_history(), cfg.get("anilist_token"))
            if not hist:
                warn("Watch history is empty.")
                state = "QUIT"
                continue
            history_modes = ["Active", "Completed", "All"]
            history_mode = globals().get("_history_filter", "Active")
            if history_mode not in history_modes:
                history_mode = "Active"
            filtered_hist = filter_history_entries(hist, history_mode)
            hopts = [format_history_entry(h) for h in filtered_hist]
            history_refresh_lock = threading.Lock()
            history_refresh_generation = [0]
            history_refresh_selected = [None]
            history_refresh_attempted = set()
            history_refresh_status = {}

            def _history_entry_key(entry):
                show = (entry or {}).get("show", {})
                media_id = get_anilist_media_id(show)
                if not media_id:
                    return None
                return (
                    str(media_id),
                    str(entry.get("translation_type", "sub")),
                )

            def _rebuild_history_view():
                nonlocal filtered_hist, hopts
                filtered_hist = filter_history_entries(hist, history_mode)
                hopts = [format_history_entry(entry) for entry in filtered_hist]

            def _set_history_refresh_status(key, status, message):
                global _needs_redraw
                with history_refresh_lock:
                    history_refresh_status[key] = {
                        "status": status,
                        "message": message,
                        "time": time.time(),
                    }
                _needs_redraw = True

            def _schedule_history_refresh(si):
                if not cfg.get("anilist_token") or not (0 <= si < len(filtered_hist)):
                    return
                entry = filtered_hist[si]
                show = entry.get("show", {})
                prepare_show_display_state(
                    show, entry.get("translation_type", "sub")
                )
                key = _history_entry_key(entry)
                with history_refresh_lock:
                    if history_refresh_selected[0] != key:
                        history_refresh_generation[0] += 1
                    history_refresh_selected[0] = key
                    if (
                        not key
                        or not show.get("_sync_enabled")
                        or key in history_refresh_attempted
                    ):
                        return
                    history_refresh_attempted.add(key)
                    generation = history_refresh_generation[0]

                def worker():
                    global _needs_redraw
                    time.sleep(0.35)
                    with history_refresh_lock:
                        if (
                            history_refresh_selected[0] != key
                            or history_refresh_generation[0] != generation
                        ):
                            history_refresh_attempted.discard(key)
                            _needs_redraw = True
                            return
                    _set_history_refresh_status(
                        key, "loading", "Refreshing AniList"
                    )
                    refreshed = refresh_history_entry_from_anilist(
                        entry, cfg.get("anilist_token")
                    )
                    if refreshed:
                        save_refreshed_history(hist)
                        with history_refresh_lock:
                            _rebuild_history_view()
                        _set_history_refresh_status(
                            key, "success", "AniList updated"
                        )
                    else:
                        _set_history_refresh_status(
                            key, "failed", "AniList refresh failed"
                        )
                    time.sleep(2)
                    with history_refresh_lock:
                        current = history_refresh_status.get(key, {})
                        if current.get("status") in ("success", "failed"):
                            history_refresh_status.pop(key, None)
                    _needs_redraw = True

                threading.Thread(
                    target=worker,
                    name="history-anilist-refresh",
                    daemon=True,
                ).start()

            def _history_footer(entry, width):
                default = "Enter/Right=open  Tab=filter  Del=delete  Esc=quit"
                key = _history_entry_key(entry)
                with history_refresh_lock:
                    refresh = dict(history_refresh_status.get(key, {}))
                status = refresh.get("status")
                if status == "loading":
                    text = (
                        f"\033[36m{_loading_frame()} Refreshing AniList"
                        f"{_RST}{_C_HINT}  │  {default}{_RST}"
                    )
                    return _fit_terminal_line(text, width)
                if status == "success":
                    text = (
                        f"\033[32mAniList updated{_RST}"
                        f"{_C_HINT}  │  {default}{_RST}"
                    )
                    return _fit_terminal_line(text, width)
                if status == "failed":
                    text = (
                        f"\033[38;5;203mAniList refresh failed{_RST}"
                        f"{_C_HINT}  │  {default}{_RST}"
                    )
                    return _fit_terminal_line(text, width)
                return _poster_footer_line(entry.get("show", {}), default, width)

            def _hist_top_hdr(si):
                if 0 <= si < len(filtered_hist):
                    show = filtered_hist[si].get("show", {})
                    globals()["_hovered_show_id"] = show.get("_id")
                    poster = _get_poster(show)
                    if poster:
                        return poster
                return ""

            def _hist_hdr(si):
                _schedule_history_refresh(si)
                try:
                    w = os.get_terminal_size().columns
                except OSError:
                    w = 80
                parts = []
                selected_show = {}
                if 0 <= si < len(filtered_hist):
                    h = filtered_hist[si]
                    tt = h.get("translation_type", "sub")
                    selected_show = h.get("show", {})
                    build_info_panel(selected_show, tt, w, parts)
                selected_entry = (
                    filtered_hist[si]
                    if 0 <= si < len(filtered_hist)
                    else {}
                )
                parts.append(_history_footer(selected_entry, w))
                return "\n".join(parts)

            def _hist_delete(si):
                nonlocal hist, filtered_hist, hopts
                if 0 <= si < len(filtered_hist):
                    h = filtered_hist[si]
                    show = h.get("show", {})
                    if delete_history_entry(show.get("_id"), h.get("translation_type", "sub")):
                        hist = load_history()
                        filtered_hist = filter_history_entries(hist, history_mode)
                        hopts = [format_history_entry(x) for x in filtered_hist]
                return hopts, _hist_hdr(0)

            def _hist_tab(_selected=None):
                nonlocal history_mode, filtered_hist, hopts
                mode_index = history_modes.index(history_mode)
                history_mode = history_modes[(mode_index + 1) % len(history_modes)]
                globals()["_history_filter"] = history_mode
                filtered_hist = filter_history_entries(hist, history_mode)
                hopts = [format_history_entry(entry) for entry in filtered_hist]
                return hopts, _hist_hdr(0)

            hidx = tui_pick(
                lambda: f"Watch History · {history_mode}", hopts,
                header_fn=_hist_hdr,
                top_header_fn=_hist_top_hdr,
                tab_fn=_hist_tab,
                delete_fn=_hist_delete,
                live_fn=lambda _query: (list(hopts), "", False),
                help_dict={
                    **picker_help("Open details", "Quit", "Quit", "Next filter"),
                    "Delete": "Remove from history"
                },
                keep_cursor_hidden_on_select=True,
                count_total=lambda: len(hist)
            )
            if hidx == -2 or hidx == -3:
                state = "QUIT"
                continue
            if hidx >= 0:
                h = filtered_hist[hidx]
                show = h.get("show", {})
                ttype = h.get("translation_type", "sub")
                prepare_show_display_state(show, ttype)
                show_id = show.get("_id")
                show_title = get_show_display_title(show)
                total_eps = show.get("availableEpisodes", {}).get(ttype, 1)
                current_ep = playback_ep_from_history_entry(h, ttype)
                episode_ids = ensure_episode_ids(show, ttype)
                total_eps = len(episode_ids) or total_eps
                current_ep_index = episode_index_for_id(episode_ids, current_ep)
                if episode_ids and current_ep_index is not None:
                    current_ep = episode_id_at(episode_ids, current_ep_index)
                elif episode_ids:
                    current_ep_index = 0
                    current_ep = episode_id_at(episode_ids, 0)
                set_ui_context(show, ttype)
                set_navigation_context("HISTORY", "HISTORY")
                state = "DETAILS"

        # ── ANILIST ───────────────────────────────────────────────────────
        elif state == "ANILIST_MENU":
            valid_statuses = ANILIST_LIST_STATUSES
            if args.anilist and args.anilist.lower() != "menu":
                req_stat = args.anilist.upper()
                stat_map = {"WATCHING": "CURRENT", "PLANNING": "PLANNING", "COMPLETED": "COMPLETED", "REWATCHING": "REPEATING", "PAUSED": "PAUSED", "DROPPED": "DROPPED", "ALL": None, "CURRENT": "CURRENT", "REPEATING": "REPEATING"}
                mapped = stat_map.get(req_stat, "INVALID")
                if mapped == "INVALID":
                    err(f"Invalid AniList status: {req_stat}")
                    state = "QUIT"
                    continue
                globals()["_anilist_browse_status"] = mapped
                state = "ANILIST_BROWSE"
                args.anilist = "menu"
                continue

            opts = list(valid_statuses.keys())
            def _menu_hdr(si):
                return anilist_menu_header()

            idx = tui_pick("AniList Lists", opts, header_fn=_menu_hdr,
                           help_dict=picker_help("Open list", "Search AllAnime", "Quit"))
            navigation = anilist_menu_navigation(idx)
            if navigation:
                if navigation == "SEARCH":
                    query_str = ""
                state = navigation
            else:
                stat_val = valid_statuses[opts[idx]]
                if stat_val == "ANILIST_SEARCH":
                    query_str = ""
                    anilist_search_parent = "ANILIST_MENU"
                    state = "ANILIST_SEARCH"
                else:
                    globals()["_anilist_browse_status"] = valid_statuses[opts[idx]]
                    state = "ANILIST_BROWSE"

        elif state == "ANILIST_BROWSE":
            stat = globals().get("_anilist_browse_status")
            al_base_shows = load_anilist_browse(cfg["anilist_token"], stat)
            if not al_base_shows:
                err("No anime found in this AniList list.")
                state = "ANILIST_MENU"
                continue

            sort_mode = normalize_anilist_sort_mode(
                cfg.get("anilist_sort", "recent")
            )
            history_for_sort = load_history()
            al_shows = sort_anilist_shows(
                al_base_shows, sort_mode, history_for_sort
            )
            opts = [f"{s['name']}" for s in al_shows]
            def _al_top_hdr(si):
                if 0 <= si < len(al_shows):
                    globals()["_hovered_show_id"] = al_shows[si].get("_id")
                    poster = _get_poster(al_shows[si])
                    if poster: return poster
                return ""

            def _al_hdr(si):
                C_K  = "\033[38;5;244m"
                R    = "\033[0m"
                try: w = os.get_terminal_size().columns
                except OSError: w = 80
                parts = []
                if 0 <= si < len(al_shows):
                    s = al_shows[si]
                    build_info_panel(s, ttype, w, parts)
                    selected_show = s
                else:
                    selected_show = {}

                parts.append(_poster_footer_line(selected_show, f"{len(al_shows)} results  │  Enter/Right=open  Tab=sort  Esc=back", w))
                return "\n".join(parts)

            def _al_tab(_selected=None):
                nonlocal sort_mode, al_shows, opts
                sort_mode = next_anilist_sort_mode(sort_mode)
                cfg["anilist_sort"] = sort_mode
                save_config(cfg)
                al_shows = sort_anilist_shows(
                    al_base_shows, sort_mode, history_for_sort
                )
                opts = [f"{show['name']}" for show in al_shows]
                return opts, _al_hdr(0)

            list_title = al_shows[0].get("_anilist_list", "Browse") if al_shows else "Browse"
            idx = tui_pick(
                lambda: (
                    f"AniList - {list_title} · "
                    f"{ANILIST_SORT_LABELS[sort_mode]}"
                ),
                opts,
                header_fn=_al_hdr,
                top_header_fn=_al_top_hdr,
                tab_fn=_al_tab,
                help_dict=picker_help(
                    "Open title", "Back to lists", "Back to lists", "Change sort"
                ),
            )
            if idx in (-2, -3):
                state = "ANILIST_MENU"
            elif idx >= 0:
                s = al_shows[idx]

                matched = with_loading(
                    "Matching title on AllAnime...",
                    match_anilist_show_to_allanime,
                    s,
                    ttype,
                )

                if matched:
                    shows = [matched]

                    set_ui_context(matched, ttype)
                    show_id    = matched["_id"]
                    show_title = get_show_display_title(matched)
                    total_eps  = matched.get("availableEpisodes",{}).get(ttype,0)
                    episode_ids = load_episode_ids_for_selection(
                        matched, ttype
                    )
                    total_eps = len(episode_ids) or total_eps

                    if args.episode:
                        current_ep = str(args.episode)
                        current_ep_index = episode_index_for_id(episode_ids, current_ep)
                        args.episode = None
                        if not episode_ids:
                            err(episode_catalog_error(matched))
                            state = "DETAILS"
                        elif current_ep_index is None:
                            err(f"EP {current_ep} is not available from this provider.")
                            state = "EPISODE"
                        else:
                            current_ep = episode_id_at(episode_ids, current_ep_index)
                            state = "PLAY"
                    else:
                        set_navigation_context("ANILIST_BROWSE", "ANILIST_BROWSE")
                        state="DETAILS"
                else:
                    matched = _run_manual_match_search(s, ttype)
                    if matched:
                        shows = [matched]
                        set_ui_context(matched, ttype)
                        show_id = matched["_id"]
                        show_title = get_show_display_title(matched)
                        total_eps = matched.get("availableEpisodes", {}).get(ttype, 0)
                        episode_ids = ensure_episode_ids(matched, ttype)
                        total_eps = len(episode_ids) or total_eps
                        current_ep_index = 0
                        current_ep = episode_id_at(episode_ids, current_ep_index)
                        set_navigation_context("ANILIST_BROWSE", "ANILIST_BROWSE")
                        state = "DETAILS"
                    else:
                        state = "ANILIST_BROWSE"

        # ── SEARCH (AllAnime Default) ─────────────────────────────────────
        elif state == "SEARCH":
            _ui_show_ctx = {}
            _ep_cache_key = None
            _ep_cache_data = None
            _clear_poster_downloads()

            # Step 1: Input Page
            if not query_str:
                hd1 = search_input_help()
                query_str = tui_pick("Search Anime", [], header_fn=_search_input_header("AllAnime"), return_query_on_enter=True, query_history=load_search_history(), is_search=True, help_dict=hd1)
                globals()["_search_error"] = ""
                if query_str == -2:
                    state = "QUIT"; continue
                if not query_str:
                    continue
                query_str = str(query_str).strip()
                just_searched = True
                save_search_history(query_str)

            if not query_str:
                err("Search query cannot be empty."); state="QUIT"; continue

            # Step 2: Fetch Results ONCE
            live_fn, get_results, get_loading, get_error = _cached_search_results(
                query_str,
                "_last_aa_query_str",
                "_last_aa_shows",
                lambda: make_allanime_oneshot_search(query_str, ttype)
            )

            # Step 3: Title Selection Page
            enter_alt_screen()

            initial_opts = [f"{s.get('name', 'Unknown')}" for s in get_results()]
            if len(initial_opts) == 1:
                idx = 0
            else:
                hd2 = picker_help("Select anime", "New search", "Quit")
                idx = tui_pick("Search Anime", initial_opts, header_fn=_search_result_header("AllAnime", query_str, ttype, get_results, get_loading), top_header_fn=_search_cover_header(get_results), live_fn=live_fn, is_search=False, help_dict=hd2, auto_select_single_when_done=just_searched)

            shows = get_results()
            _remember_search_results(query_str, shows, "_last_aa_query_str", "_last_aa_shows")

            if idx == -2:
                state = "QUIT"
            elif idx == -3:
                query_str = ""
            elif idx == -4:
                globals()["_search_error"] = (
                    get_error() or f'No results found for "{query_str}"'
                )
                query_str = ""
                continue
            elif isinstance(idx, str):
                if idx.strip():
                    query_str = idx.strip()
                continue
            else:
                s = shows[idx]
                show_id = s["_id"]
                show_title = get_show_display_title(s)
                total_eps = s.get("availableEpisodes", {}).get(ttype, 0)
                episode_ids = load_episode_ids_for_selection(s, ttype)
                total_eps = len(episode_ids) or total_eps

                set_ui_context(s, ttype)
                set_navigation_context("SEARCH", "SEARCH")

                h = next((x for x in load_history() if x.get("show", {}).get("_id") == show_id and x.get("translation_type") == ttype), None)
                if h:
                    current_ep = playback_ep_from_history_entry(h, ttype)
                else:
                    current_ep = episode_id_at(episode_ids, 0)
                current_ep_index = episode_index_for_id(episode_ids, current_ep)
                if episode_ids and current_ep_index is not None:
                    current_ep = episode_id_at(episode_ids, current_ep_index)
                elif episode_ids:
                    current_ep_index = 0
                    current_ep = episode_id_at(episode_ids, 0)

                # Smart Play Logic
                if resolveTracking(state, args, cfg, s) and cfg.get("anilist_token"):
                    matched = with_loading(
                        f"Matching AniList: {s['name']}",
                        match_allanime_show_to_anilist,
                        s,
                        cfg["anilist_token"],
                    )
                    if not matched:
                        matched = _run_manual_anilist_match(s, cfg["anilist_token"])
                    if matched:
                        set_title_sync(s, True)
                        prepare_show_display_state(s, ttype, True)
                        state = "DETAILS"
                        continue
                    query_str = ""
                    state = "SEARCH"
                    continue

                # If no Smart Play, go to Episodes list
                state = "EPISODE"



        # ── ANILIST_SEARCH ────────────────────────────────────────────────
        elif state == "ANILIST_SEARCH":
            _ui_show_ctx = {}
            _ep_cache_key = None
            _ep_cache_data = None
            _clear_poster_downloads()

            # Step 1: Input Page
            if not query_str:
                esc_action = "back" if anilist_search_parent != "QUIT" else "quit"
                query_str = tui_pick(
                    "Search Anime", [],
                    header_fn=_search_input_header("AniList", esc_action),
                    return_query_on_enter=True,
                    query_history=load_search_history(),
                    is_search=True,
                    help_dict=picker_help(
                        "Search",
                        "Move cursor left",
                        "Back" if anilist_search_parent != "QUIT" else "Quit",
                    ),
                )
                globals()["_search_error"] = ""
                if query_str == -2:
                    state = anilist_search_parent
                    continue
                if not query_str:
                    continue
                query_str = str(query_str).strip()
                just_searched = True
                save_search_history(query_str)

            if not query_str:
                err("Search query cannot be empty."); state="QUIT"; continue

            # Step 2: Fetch Results ONCE
            live_fn, get_results, get_loading, get_error = _cached_search_results(
                query_str,
                "_last_query_str",
                "_last_shows",
                lambda: make_anilist_oneshot_search(cfg.get("anilist_token"), query_str)
            )

            # Step 3: Title Selection Page
            enter_alt_screen()

            initial_opts = [f"{s.get('name', 'Unknown')}" for s in get_results()]
            esc_action = "back" if anilist_search_parent != "QUIT" else "quit"
            if len(initial_opts) == 1:
                idx = 0
            else:
                hd4 = picker_help(
                    "Select anime",
                    "New search",
                    "Back" if anilist_search_parent != "QUIT" else "Quit",
                )
                idx = tui_pick(
                    "Search Anime", initial_opts,
                    header_fn=_search_result_header(
                        "AniList", query_str, ttype, get_results, get_loading,
                        esc_action
                    ),
                    top_header_fn=_search_cover_header(get_results),
                    live_fn=live_fn,
                    is_search=False,
                    help_dict=hd4,
                    auto_select_single_when_done=just_searched,
                )

            shows = get_results()
            _remember_search_results(query_str, shows, "_last_query_str", "_last_shows")

            if idx == -2:
                state = anilist_search_parent
            elif idx == -3:
                query_str = ""
            elif idx == -4:
                globals()["_search_error"] = (
                    get_error() or f'No results found for "{query_str}"'
                )
                query_str = ""
                continue
            elif isinstance(idx, str):
                if idx.strip():
                    query_str = idx.strip()
                continue
            else:
                s = shows[idx]

                matched = with_loading(
                    "Matching title on AllAnime...",
                    match_anilist_show_to_allanime,
                    s,
                    ttype,
                )

                if matched:
                    set_ui_context(matched, ttype)
                    total_eps = matched.get("availableEpisodes", {}).get(ttype, 0)
                    show_id = matched.get("_id")
                    show_title = get_show_display_title(matched)
                    episode_ids = load_episode_ids_for_selection(matched, ttype)
                    total_eps = len(episode_ids) or total_eps

                    h = next((x for x in load_history() if x.get("show", {}).get("_id") == show_id and x.get("translation_type") == ttype), None)
                    if h:
                        current_ep = playback_ep_from_history_entry(h, ttype)
                    else:
                        current_ep = episode_id_at(episode_ids, 0)
                    current_ep_index = episode_index_for_id(episode_ids, current_ep)
                    if episode_ids and current_ep_index is not None:
                        current_ep = episode_id_at(episode_ids, current_ep_index)
                    elif episode_ids:
                        current_ep_index = 0
                        current_ep = episode_id_at(episode_ids, 0)

                    set_navigation_context("ANILIST_SEARCH", "ANILIST_SEARCH")

                    state = "DETAILS"
                else:
                    matched = _run_manual_match_search(s, ttype)
                    if matched:
                        set_ui_context(matched, ttype)
                        total_eps = matched.get("availableEpisodes", {}).get(ttype, 0)
                        show_id = matched.get("_id")
                        show_title = get_show_display_title(matched)
                        episode_ids = load_episode_ids_for_selection(
                            matched, ttype
                        )
                        total_eps = len(episode_ids) or total_eps
                        current_ep_index = 0
                        current_ep = episode_id_at(episode_ids, current_ep_index)
                        set_navigation_context("ANILIST_SEARCH", "ANILIST_SEARCH")
                        state = "DETAILS"
                    else:
                        if len(shows) == 1:
                            query_str = ""
                        continue

        # ── DETAILS ───────────────────────────────────────────────────────
        elif state == "DETAILS":
            s = get_ui_show()
            ttype = get_ui_ttype()
            episode_ids = ensure_episode_ids(s, ttype)
            total_eps = len(episode_ids) or total_eps
            current_ep_index = episode_index_for_id(episode_ids, current_ep)
            if current_ep_index is None:
                current_ep_index = 0
                if episode_ids:
                    current_ep = episode_id_at(episode_ids, 0)

            from_anilist = get_search_prev(None) in ("ANILIST_BROWSE", "ANILIST_SEARCH")
            s["_anilist_context"] = from_anilist
            use_anilist = bool(resolveTracking(get_search_prev(), args, cfg, s) and s.get("_anilist_id"))
            prepare_show_display_state(s, ttype, use_anilist)
            local_before = get_local_progress(s, ttype)
            try:
                remote_before = int(s.get("_anilist_progress") or 0)
            except (TypeError, ValueError):
                remote_before = 0
            if s.get("_anilist_id") and (from_anilist or use_anilist):
                if use_anilist and local_before is not None and local_before != remote_before:
                    reconcile_result = with_loading(
                        "Reconciling local and AniList progress…",
                        reconcile_progress,
                        s, ttype, cfg.get("anilist_token"),
                        anilist_source=from_anilist,
                        sync_enabled=use_anilist,
                    )
                else:
                    reconcile_result = reconcile_progress(
                        s, ttype, cfg.get("anilist_token"),
                        anilist_source=from_anilist,
                        sync_enabled=use_anilist,
                    )
            else:
                reconcile_result = {"action": "local"}
            prepare_show_display_state(s, ttype, use_anilist)
            local_progress = get_local_progress(s, ttype)
            try:
                al_progress = int(s.get("_anilist_progress") or 0)
            except (TypeError, ValueError):
                al_progress = 0
            prog = local_progress if local_progress is not None else 0

            total = s.get("episodeCount")
            try: total = int(total) if total is not None else 0
            except ValueError: total = 0

            released = s.get("availableEpisodes", {}).get(ttype, 0)
            try: released = int(released) if released is not None else 0
            except ValueError: released = 0
            nep = s.get("_next_airing_ep")
            if nep is not None:
                try:
                    inferred = int(nep) - 1
                    if inferred > released: released = inferred
                except ValueError: pass

            api_status = str(s.get("status", "")).upper()
            user_status = str(s.get("_anilist_list", "")).upper()
            playback_status = user_status if use_anilist else ""
            player = args.player or cfg.get("player", "mpv")
            isDesktop = player in ["mpv", "mpvex"] and not termux

            opts = []
            detail_play_ep = episode_id_at(episode_ids, 0) if episode_ids else None
            detail_next_ep = episode_id_at(
                episode_ids,
                min(max(int(prog), 0), max(0, total_eps - 1)),
            ) if episode_ids else None
            detail_max_progress = max(released, prog, episode_progress_number(episode_ids[-1], len(episode_ids)) if episode_ids else 0)
            next_manual_progress = prog + 1
            sync_conflict = s.get("_sync_conflict") or {}

            if sync_conflict:
                opts.extend(["Keep Local Progress", "Use AniList Progress"])
            elif episode_ids and (playback_status == "COMPLETED" or (total and prog >= total)):
                opts.append("Rewatch")
                if total != 1 and isDesktop: opts.append("Binge (from start)")
            elif episode_ids and prog == 0:
                opts.append("Play")
                if total != 1 and isDesktop: opts.append("Binge")
            elif episode_ids and prog > 0 and released and prog < released:
                opts.append("Next")
                if (released - prog) > 1 and isDesktop: opts.append("Binge (from next)")
            elif (episode_ids and prog > 0 and released
                    and prog >= released and api_status == "RELEASING"):
                if isDesktop: opts.append("Binge (from start)")

            if episode_ids:
                opts.append("Episodes")
            elif not s.get("_action_feedback"):
                set_action_feedback(s, episode_catalog_error(s))
            if from_anilist and s.get("_anilist_id"):
                opts.append("Match AllAnime")
            elif cfg.get("anilist_token") and s.get("_id"):
                opts.append("Match AniList")
            if cfg.get("anilist_token") and not is_incognito():
                if s.get("_anilist_id"):
                    if (use_anilist
                            and detail_max_progress
                            and next_manual_progress <= detail_max_progress
                            and next_manual_progress > al_progress):
                        opts.append("Mark Next Watched")
                    opts.append("Set Progress")
                    if not from_anilist:
                        opts.append(f"AniList Sync: {'On' if use_anilist else 'Off'}")
                    opts.extend(["Status", "Score"])
            opts.extend(["Back", "Quit"])

            hints = {
                "Play": f"play EP {detail_play_ep}",
                "Binge": f"binge from EP {detail_play_ep}",
                "Next": f"play EP {detail_next_ep}",
                "Keep Local Progress": f"sync local EP {sync_conflict.get('local', 0)}",
                "Use AniList Progress": f"import AL EP {sync_conflict.get('anilist', 0)}",
                "Binge (from next)": f"binge from EP {detail_next_ep}",
                "Binge (from start)": f"binge from EP {detail_play_ep}",
                "Rewatch": f"replay from EP {detail_play_ep}",
                "Episodes": "choose episode",
                "Match AllAnime": "link a different streaming title",
                "Match AniList": "link a different tracking title",
                "Mark Next Watched": f"sync EP {min(next_manual_progress, detail_max_progress) if detail_max_progress else next_manual_progress}",
                "Set Progress": "update progress",
                "AniList Sync: On": "disable persistent sync",
                "AniList Sync: Off": "enable persistent sync",
                "Status": "update status",
                "Score": "update score",
                "Back": "return to previous screen",
                "Quit": "exit program"
            }

            def _details_hdr(si):
                C_K = "\033[38;5;244m"
                R = "\033[0m"
                try: w = os.get_terminal_size().columns
                except OSError: w = 80
                parts = []
                build_info_panel(s, ttype, w, parts)
                direct_single = (
                    get_search_prev() in ("SEARCH", "ANILIST_SEARCH")
                    and len(shows) <= 1
                    and just_searched
                )
                nav_text = "Left=search  Esc=quit" if direct_single else "Left/Esc=back"
                if direct_single and get_search_prev() == "ANILIST_SEARCH":
                    nav_text = (
                        "Left=search  Esc="
                        + ("back" if anilist_search_parent != "QUIT" else "quit")
                    )
                parts.append(_poster_footer_line(s, f"Enter/Right=select  ? = Help  {nav_text}", w))
                return "\n".join(parts)

            direct_single = (
                get_search_prev() in ("SEARCH", "ANILIST_SEARCH")
                and len(shows) <= 1
                and just_searched
            )
            hd5 = picker_help(
                "Select option",
                "New search" if direct_single else "Go back",
                (
                    "Back"
                    if direct_single
                    and get_search_prev() == "ANILIST_SEARCH"
                    and anilist_search_parent != "QUIT"
                    else "Quit"
                ) if direct_single else "Go back"
            )
            idx = tui_pick(f"Anime Details", opts, header_fn=_details_hdr, hints=hints, help_dict=hd5)

            if idx == -2:
                previous = get_search_prev()
                if direct_single:
                    query_str = ""
                    state = (
                        anilist_search_parent
                        if previous == "ANILIST_SEARCH"
                        else "QUIT"
                    )
                else:
                    state = previous
                continue
            if idx == -3:
                previous = get_search_prev()
                if should_clear_query_on_child_left(
                        previous, direct_single):
                    query_str = ""
                state = previous
                continue

            if idx >= 0:
                opt = opts[idx]
                if opt in ["Play", "Next", "Rewatch"]:
                    args.binge = False
                    set_navigation_context(action_prev="DETAILS")
                    if opt == "Next":
                        current_ep_index = min(max(int(prog), 0), max(0, total_eps - 1))
                        current_ep = episode_id_at(episode_ids, current_ep_index)
                    elif opt == "Rewatch":
                        if use_anilist:
                            reset_result = with_loading(
                                "Starting AniList rewatch…",
                                _push_local_progress,
                                s, ttype, cfg.get("anilist_token"), 0
                            )
                            if reset_result.get("action") == "failed":
                                err("Could not start AniList rewatch.")
                                state = "DETAILS"
                                continue
                        else:
                            write_history_progress(s, 0, ttype, touch=False)
                        current_ep_index = 0
                        current_ep = episode_id_at(episode_ids, current_ep_index)
                    else:
                        if use_anilist:
                            current_ep_index = 0
                            current_ep = episode_id_at(episode_ids, current_ep_index)
                        else:
                            h = next((x for x in load_history() if str(x.get("show", {}).get("_id")) == str(s.get("_id")) and x.get("translation_type") == ttype), None)
                            if h:
                                current_ep = playback_ep_from_history_entry(h, ttype)
                            else:
                                current_ep = episode_id_at(episode_ids, 0)
                            current_ep_index = episode_index_for_id(episode_ids, current_ep)
                            if current_ep_index is None:
                                current_ep_index = 0
                            current_ep = episode_id_at(episode_ids, current_ep_index)
                    state = "PLAY"
                elif opt == "Keep Local Progress":
                    result = with_loading(
                        f"Syncing local progress: EP {sync_conflict.get('local', 0)}…",
                        _push_local_progress,
                        s, ttype, cfg.get("anilist_token"), sync_conflict.get("local", 0)
                    )
                    if result.get("action") == "failed":
                        err("AniList sync failed. Local progress was preserved.")
                    state = "DETAILS"
                elif opt == "Use AniList Progress":
                    _import_anilist_progress(
                        s, ttype, sync_conflict.get("anilist", 0),
                        authority="AL"
                    )
                    state = "DETAILS"
                elif opt.startswith("Binge"):
                    args.binge = True
                    set_navigation_context(action_prev="DETAILS")
                    if "(from next)" in opt:
                        current_ep_index = min(max(int(prog), 0), max(0, total_eps - 1))
                        current_ep = episode_id_at(episode_ids, current_ep_index)
                    elif "(from start)" in opt or opt == "Binge":
                        if "(from start)" in opt and playback_status == "COMPLETED":
                            if use_anilist:
                                reset_result = with_loading(
                                    "Starting AniList rewatch…",
                                    _push_local_progress,
                                    s, ttype, cfg.get("anilist_token"), 0
                                )
                                if reset_result.get("action") == "failed":
                                    err("Could not start AniList rewatch.")
                                    state = "DETAILS"
                                    continue
                            else:
                                write_history_progress(s, 0, ttype, touch=False)
                        current_ep_index = 0
                        current_ep = episode_id_at(episode_ids, current_ep_index)
                    state = "PLAY"
                elif opt == "Episodes":
                    set_navigation_context(ep_prev="DETAILS")
                    state = "EPISODE"
                elif opt == "Match AllAnime":
                    al_show = {
                        "_id": s.get("_anilist_id"),
                        "name": s.get("_display_name") or s.get("name", ""),
                        "englishName": s.get("_display_english_name") or s.get("englishName", ""),
                        "_anilist_list": s.get("_anilist_list"),
                        "_anilist_progress": s.get("_anilist_progress"),
                        "_next_airing_ep": s.get("_next_airing_ep"),
                        "_next_airing_time": s.get("_next_airing_time"),
                        "_next_airing_at": s.get("_next_airing_at"),
                        "thumbnail": s.get("thumbnail")
                    }
                    new_match = _run_manual_match_search(al_show, ttype)
                    if new_match:
                        set_title_sync(new_match, use_anilist)
                        prepare_show_display_state(new_match, ttype, use_anilist)
                        set_ui_context(new_match, ttype)
                        show_id = new_match.get("_id")
                        show_title = get_show_display_title(new_match)
                        total_eps = new_match.get("availableEpisodes", {}).get(ttype, 0)
                        episode_ids = ensure_episode_ids(new_match, ttype)
                        total_eps = len(episode_ids) or total_eps
                        current_ep_index = 0
                        current_ep = episode_id_at(episode_ids, current_ep_index)
                    state = "DETAILS"
                elif opt == "Match AniList":
                    matched = _run_manual_anilist_match(s, cfg["anilist_token"])
                    if matched:
                        set_title_sync(s, True)
                        prepare_show_display_state(s, ttype, True)
                        show_title = get_show_display_title(s, sync_enabled=True)
                    state = "DETAILS"
                elif opt == "Mark Next Watched":
                    al_id = s.get("_anilist_id")
                    max_progress = max(released, prog, episode_progress_number(episode_ids[-1], len(episode_ids)) if episode_ids else 0)
                    next_progress = min(prog + 1, max_progress) if max_progress else prog + 1
                    status_value = tracking_status_for_progress(s, next_progress)
                    updated = False
                    if al_id:
                        updated = with_loading(
                            f"Syncing AniList progress: EP {next_progress}…",
                            update_anilist_entry,
                            cfg["anilist_token"],
                            int(al_id),
                            progress=next_progress,
                            status=status_value
                        )
                    if updated:
                        apply_tracking_progress_local(s, next_progress, status_value)
                        write_history_progress(
                            s, next_progress, ttype,
                            last_synced=next_progress,
                            touch=True,
                        )
                        s["_progress_authority"] = "AL"
                        set_action_feedback(s, f"AniList synced: EP {next_progress} watched.")
                    else:
                        err("AniList sync failed.")
                    state = "DETAILS"
                elif opt == "Set Progress":
                    state = "UPDATE_PROGRESS"
                elif opt.startswith("AniList Sync:"):
                    new_sync = not bool(use_anilist)
                    args.sync = False
                    args.no_sync = False
                    globals()["SYNC_FORCE_ON"] = False
                    globals()["SYNC_FORCE_OFF"] = False
                    set_title_sync(s, new_sync)
                    prepare_show_display_state(s, ttype, new_sync)
                    s["_progress_authority"] = "AL" if new_sync else "LOCAL"
                    show_title = get_show_display_title(s, sync_enabled=new_sync)
                    state = "DETAILS"
                elif opt == "Status":
                    state = "UPDATE_STATUS"
                elif opt == "Score":
                    state = "UPDATE_SCORE"
                elif opt == "Back":
                    previous = get_search_prev()
                    if direct_single:
                        query_str = ""
                    state = previous
                    continue
                elif opt == "Quit":
                    state = "QUIT"
                    continue

        # ── UPDATE_PROGRESS ───────────────────────────────────────────────
        elif state == "UPDATE_PROGRESS":
            s = get_ui_show()
            ttype = get_ui_ttype()
            episode_ids = ensure_episode_ids(s, ttype)
            try:
                prog = int(s.get("_anilist_progress") or 0)
            except ValueError:
                prog = 0
            released = s.get("availableEpisodes", {}).get(ttype, 0)
            try:
                released = int(released) if released is not None else 0
            except ValueError:
                released = 0
            max_progress = max(released, prog, episode_progress_number(episode_ids[-1], len(episode_ids)) if episode_ids else 0)
            if max_progress <= 0:
                max_progress = max(prog, 1)

            def _progress_hdr(si):
                try: w = os.get_terminal_size().columns
                except OSError: w = 80
                parts = []
                build_info_panel(s, ttype, w, parts)
                parts.append(_poster_footer_line(s, "Enter/Right=set progress  Tab=flip  ? = Help  Left/Esc=back", w))
                return "\n".join(parts)

            progress_order = list(range(max_progress, -1, -1))

            def _progress_label(p):
                label = f"{p}/{max_progress}"
                if p <= prog:
                    return f"\033[38;5;244m{label}\033[0m"
                return label

            progress_opts = [_progress_label(p) for p in progress_order]
            progress_hints = {}
            for p in progress_order:
                key = f"{p}/{max_progress}"
                if p == prog:
                    progress_hints[key] = "current"
                elif p < prog:
                    progress_hints[key] = "lower progress"
                else:
                    progress_hints[key] = "sync to AniList"

            def _progress_tab_fn(opt=None):
                nonlocal progress_order, progress_opts
                progress_order.reverse()
                progress_opts = [_progress_label(p) for p in progress_order]
                return (progress_opts, _progress_hdr(0))

            hd9 = picker_help("Set progress", "Go back", "Go back", "Flip order")
            idx = tui_pick("Set AniList Progress", progress_opts, header_fn=_progress_hdr, hints=progress_hints, tab_fn=_progress_tab_fn, help_dict=hd9)
            if idx >= 0:
                al_id = s.get("_anilist_id")
                next_progress = progress_order[idx]
                status_value = tracking_status_for_progress(s, next_progress) if next_progress > 0 else None
                updated = False
                if al_id:
                    updated = with_loading(
                        f"Syncing AniList progress: EP {next_progress}…",
                        update_anilist_entry,
                        cfg["anilist_token"],
                        int(al_id),
                        progress=next_progress,
                        status=status_value
                    )
                if updated:
                    apply_tracking_progress_local(s, next_progress, status_value)
                    if resolveTracking(get_search_prev(), args, cfg, s):
                        write_history_progress(
                            s, next_progress, ttype,
                            last_synced=next_progress,
                            touch=True,
                        )
                        s["_progress_authority"] = "AL"
                    set_action_feedback(s, f"AniList synced: EP {next_progress} watched.")
                else:
                    err("AniList sync failed.")
            state = "DETAILS"

        # ── UPDATE_STATUS ─────────────────────────────────────────────────
        elif state == "UPDATE_STATUS":
            s = get_ui_show()
            ttype = get_ui_ttype()
            def _status_hdr(si):
                C_K = "\033[38;5;244m"
                R = "\033[0m"
                try: w = os.get_terminal_size().columns
                except OSError: w = 80
                parts = []
                build_info_panel(s, ttype, w, parts)
                parts.append(_poster_footer_line(s, "Enter/Right=select  ? = Help  Left/Esc=back", w))
                return "\n".join(parts)
            status_choices = [
                ("Watching", "CURRENT"),
                ("Rewatching", "REPEATING"),
                ("Planning", "PLANNING"),
                ("Completed", "COMPLETED"),
                ("Dropped", "DROPPED"),
                ("Paused", "PAUSED"),
            ]
            opts = [label for label, _status in status_choices]
            hd7 = picker_help("Select status", "Go back", "Go back")
            idx = tui_pick("Update AniList Status", opts, header_fn=_status_hdr, help_dict=hd7)
            if idx >= 0:
                s = get_ui_show()
                al_id = s.get("_anilist_id")
                if al_id:
                    label, status_value = status_choices[idx]
                    progress_value = None
                    if status_value == "COMPLETED":
                        progress_value = completed_media_total(s, ttype)
                        if not progress_value:
                            err("This anime is not finished or its total EP count is unknown.")
                            state = "DETAILS"
                            continue
                    updated = with_loading(
                        f"Updating AniList status: {label}",
                        update_anilist_entry,
                        cfg["anilist_token"],
                        int(al_id),
                        progress=progress_value,
                        status=status_value
                    )
                    if updated:
                        s["_anilist_list"] = status_value
                        if progress_value is not None:
                            apply_tracking_progress_local(s, progress_value, status_value)
                            write_history_progress(
                                s, progress_value, ttype,
                                last_synced=progress_value,
                                touch=True,
                            )
                            s["_progress_authority"] = "AL"
                            set_action_feedback(
                                s,
                                f"AniList completed: EP {progress_value} watched."
                            )
                    else:
                        err(f"Could not update AniList status to {label}.")
            state = "DETAILS"

        # ── UPDATE_SCORE ──────────────────────────────────────────────────
        elif state == "UPDATE_SCORE":
            s = get_ui_show()
            ttype = get_ui_ttype()
            def _score_hdr(si):
                C_K = "\033[38;5;244m"
                R = "\033[0m"
                try: w = os.get_terminal_size().columns
                except OSError: w = 80
                parts = []
                build_info_panel(s, ttype, w, parts)
                parts.append(_poster_footer_line(s, "Enter/Right=select  ? = Help  Left/Esc=back", w))
                return "\n".join(parts)
            opts = [str(i) for i in range(10, 0, -1)]
            hd8 = picker_help("Select score", "Go back", "Go back")
            idx = tui_pick("Update Score", opts, header_fn=_score_hdr, help_dict=hd8)
            if idx >= 0:
                s = get_ui_show()
                al_id = s.get("_anilist_id")
                if al_id:
                    updated = with_loading(f"Updating AniList score: {opts[idx]}/10", update_anilist_entry, cfg["anilist_token"], int(al_id), score=int(opts[idx]) * 10) # 100-point scale internally
                    if not updated:
                        err(f"Could not update AniList score to {opts[idx]}/10.")
            state = "DETAILS"

        # ── EPISODE ───────────────────────────────────────────────────────
        elif state == "EPISODE":
            show = get_ui_show()
            episode_ids = ensure_episode_ids(show, ttype)
            if not episode_ids:
                err(episode_catalog_error(show))
                state = get_ep_prev("DETAILS")
                continue
            total_eps = len(episode_ids) or total_eps
            display_order = list(range(len(episode_ids)))
            if get_episode_order(show_id, cfg.get("episode_order", "asc")) == "desc":
                display_order.reverse()
            ep_opts = [episode_label(episode_ids[i]) for i in display_order]
            def _ep_hdr(si):
                C_K  = "\033[38;5;244m"
                R    = "\033[0m"
                try:
                    w = os.get_terminal_size().columns
                except OSError:
                    w = 80
                parts = []
                show = get_ui_show()
                tt = get_ui_ttype()

                if show:
                    build_info_panel(show, tt, w, parts)

                _t = lambda s: _truncate_display(s, max(1, w - 1))
                direct_single = get_ep_prev() == "SEARCH" and len(shows) <= 1 and just_searched
                nav_text = "Left=search  Esc=quit" if direct_single else "Left/Esc=back"
                parts.append(f"{C_K}{_t(f'Enter/Right=select  ? = Help  {nav_text}')}{R}")


                return "\n".join(parts)

            def _ep_tab_fn(opt=None):
                nonlocal ep_opts, display_order
                toggle_episode_order(show_id, cfg.get("episode_order", "asc"))
                display_order.reverse()
                ep_opts = [episode_label(episode_ids[i]) for i in display_order]
                return (ep_opts, _ep_hdr(0))

            if total_eps <= 1:
                idx = 0
            else:
                direct_single = get_ep_prev() == "SEARCH" and len(shows) <= 1 and just_searched
                hd6 = picker_help(
                    "Play episode",
                    "New search" if direct_single else "Go back",
                    "Quit" if direct_single else "Go back",
                    "Flip order"
                )
                idx = tui_pick("Select episode", ep_opts, header_fn=_ep_hdr, tab_fn=_ep_tab_fn, help_dict=hd6)

            if idx == -2:
                previous = get_ep_prev()
                if previous == "SEARCH" and len(shows) <= 1 and just_searched:
                    state = "QUIT"
                else:
                    state = previous
            elif idx == -3:
                previous = get_ep_prev()
                if should_clear_query_on_child_left(
                        previous, direct_single):
                    query_str = ""
                state = previous
            else:
                current_ep_index = display_order[idx]
                current_ep = episode_id_at(episode_ids, current_ep_index)
                set_navigation_context(action_prev="EPISODE")
                selected_stream = None
                _clear_streams()   # reset for new episode
                state           = "PLAY"

        # ── PLAY ──────────────────────────────────────────────────────────
        elif state == "PLAY":
            enter_alt_screen()

            s_ctx = get_ui_show()
            sync_enabled = resolveTracking(get_search_prev(), args, cfg, s_ctx)
            prepare_show_display_state(s_ctx, ttype, sync_enabled)
            show_title = get_show_display_title(s_ctx, sync_enabled=sync_enabled)
            show_id = s_ctx.get("_id")
            al_id = s_ctx.get("_anilist_id")
            episode_ids = ensure_episode_ids(s_ctx, ttype)
            if not episode_ids:
                _exit_player_screen()
                err(episode_catalog_error(s_ctx))
                state = "DETAILS"
                continue
            total_eps = len(episode_ids) or total_eps
            current_ep_index = episode_index_for_id(episode_ids, current_ep)
            if current_ep_index is None:
                _exit_player_screen()
                err(f"EP {current_ep} is not present in the provider catalog.")
                state = "EPISODE"
                continue
            current_ep = episode_id_at(episode_ids, current_ep_index)

            _player_ui_state.update({
                "active": True,
                "show": get_ui_show(),
                "current_ep": current_ep,
                "total_eps": total_eps,
                "status_lines": [],
                "stream_info": {},
                "mpv_props": None
            })

            # Instantly draw the UI so the user isn't staring at a blank screen
            if "render_player_screen" in globals():
                globals()["render_player_screen"]()

            _cache_key = (show_id, current_ep, ttype)
            if _cache_key == _ep_cache_key and _ep_cache_data:
                ep_data = _ep_cache_data
            else:
                info(f"Loading EP {current_ep} metadata...")
                ep_data = get_episode_data(show_id, current_ep, ttype)
                _ep_cache_key  = _cache_key
                _ep_cache_data = ep_data

            if not ep_data:
                _exit_player_screen()
                err(f"Could not load EP {current_ep}.")
                state="ACTION_MENU"; continue

            first_source_name = None
            if selected_stream is None:
                # Reset shared state for this episode
                _clear_streams()

                if _ipc_player.prefetched_ep == current_ep and _ipc_player.prefetched_res:
                    res = _ipc_player.prefetched_res
                    _ipc_player.prefetched_ep = None
                    _ipc_player.prefetched_stream = None
                    _ipc_player.prefetched_res = None
                else:
                    info("Finding a playable stream...")
                    res = fetch_episode_stream(show_id, current_ep, ttype, cfg.get("quality", "best"))

                if res:
                    selected_stream, first_source_name, _, streams = res
                    _extend_streams(streams)

            if args.sources and not globals().get("_initial_sources_prompted"):
                globals()["_initial_sources_prompted"] = True
                if first_source_name is not None:
                    start_bg_resolve(ep_data, {first_source_name})
                _exit_player_screen()
                state = "MIRRORS"
                continue

            if selected_stream is None:
                _exit_player_screen()
                err("No playable streams found.")
                state="ACTION_MENU"; continue

            if args.print_url:
                _exit_player_screen(close_alt=True)
                print(selected_stream["link"])
                audio_url = selected_stream.get("audio_url", "")
                if audio_url:
                    print(f"Audio: {audio_url}")
                ref = selected_stream.get("referer","")
                if ref: print(f"Referer: {ref}")
                state="QUIT"; continue

            if getattr(args, 'download', False):
                _exit_player_screen(close_alt=True)
                download_ok = download_episode(show_title, current_ep, selected_stream, cfg.get("download_dir", ""))
                if not download_ok:
                    print(f"\n{YELLOW}Download stopped at EP {current_ep}.{RESET}")
                    state="QUIT"
                    continue

                if globals().get("_download_batch_end", current_ep) > int(float(str(current_ep))) and current_ep_index + 1 < total_eps:
                    current_ep_index += 1
                    current_ep = episode_id_at(episode_ids, current_ep_index)
                    selected_stream = None
                    _clear_streams()
                    continue
                else:
                    print(f"\n{GREEN}Downloads complete.{RESET}")
                    state="QUIT"
                    continue

            # ── Launch player ─────────────────────────────────────────────
            def fetch_cb(ep_num):
                if isinstance(ep_num, int) and 1 <= ep_num <= len(episode_ids):
                    ep_idx = ep_num - 1
                else:
                    ep_idx = episode_index_for_id(episode_ids, ep_num)
                if ep_idx is None:
                    return None
                return fetch_episode_stream(show_id, episode_id_at(episode_ids, ep_idx), ttype, cfg.get("quality", "best"))
            is_binge = args.binge or cfg.get("binge", False)

            if termux:
                player = args.player or cfg.get("player","mpv")
                if player=="mpv" and not args.player:
                    if (not pkg_installed("is.xyz.mpv")
                            and pkg_installed("app.marlboroadvance.mpvex")):
                        player = "mpvex"

                result = play_android(show_title, current_ep, selected_stream, fetch_cb, player, total_eps, show_id, is_binge)
                # Intentionally not saving history here for Termux. Users must explicitly click "Mark as Watched".

                # am-start returns immediately if not binge mode → player is now running.
                # Start background resolver NOW: we have the whole episode
                # watch-time to resolve remaining sources.
                # Only start if we haven't already resolved everything and
                # the bg thread isn't already running.
                if first_source_name is not None:
                    exclude = {first_source_name}
                    start_bg_resolve(ep_data, exclude)

                if result == "NEXT" and current_ep_index + 1 < total_eps:
                    current_ep_index += 1
                    current_ep = episode_id_at(episode_ids, current_ep_index)
                    selected_stream = None
                    _clear_streams()
                    continue
                elif result == "PREV" and current_ep_index > 0:
                    current_ep_index -= 1
                    current_ep = episode_id_at(episode_ids, current_ep_index)
                    selected_stream = None
                    _clear_streams()
                    continue
                _exit_player_screen()
                state = "ACTION_MENU"

            else:
                # Desktop: start bg resolve BEFORE the blocking mpv call so
                # mirrors resolve in parallel while the user watches.
                if first_source_name is not None:
                    exclude = {first_source_name}
                    start_bg_resolve(ep_data, exclude)

                next_episode = episode_id_at(episode_ids, current_ep_index + 1) if current_ep_index + 1 < total_eps else None
                result, percent, time_pos, duration, played_seconds = play_desktop(
                    show_title, current_ep, selected_stream, fetch_cb,
                    total_eps, is_binge, show_id, pending_osd_msg,
                    current_ep_index, next_episode
                )
                pending_osd_msg = ""
                _exit_player_screen()

                # Smart Auto-Scrobble & Timestamping (80% OR <150s remaining)
                auto_scrobbled = playback_looks_complete(
                    result, percent, time_pos, duration, played_seconds
                )
                pending_completion = get_pending_completion(show_id)
                if (pending_completion
                        and str(pending_completion.get("next_episode")) == str(current_ep)
                        and str(pending_completion.get("episode")) != str(current_ep)
                        and time_pos >= 120):
                    pending_ep = pending_completion.get("episode")
                    pending_progress = int(pending_completion.get("progress") or 0)
                    sync_pending = resolveTracking(get_search_prev(), args, cfg)
                    if sync_pending:
                        tkn = cfg.get("anilist_token")
                        if tkn and pending_progress:
                            show_ctx = get_ui_show()
                            new_status = tracking_status_for_progress(show_ctx, pending_progress)
                            def _pending_sync_success(ep=pending_ep, ctx=show_ctx):
                                set_action_feedback(ctx, f"AniList synced: EP {ep} watched.")
                            def _pending_sync_failure(ctx=show_ctx):
                                set_action_feedback(ctx, "Saved locally, but AniList sync is pending.")
                            queued = queue_anilist_progress(
                                tkn, show_title, pending_progress, al_id,
                                show_ctx, ttype, new_status,
                                on_success=_pending_sync_success,
                                on_failure=_pending_sync_failure,
                                pending_completion={
                                    "show_id": str(show_id),
                                    "episode": str(pending_ep),
                                },
                            )
                            if queued:
                                set_action_feedback(show_ctx, f"AniList sync queued: EP {pending_ep}.")
                        else:
                            sync_pending = False
                    if not sync_pending:
                        save_resume_time(show_id, pending_ep, 0)
                        clear_pending_completion(show_id)

                should_update_history = playback_updates_history(
                    result, percent, time_pos, duration, played_seconds
                )
                if should_update_history:
                    save_history(get_ui_show(), current_ep, ttype)

                if auto_scrobbled:
                    save_resume_time(show_id, current_ep, 0) # Clear resume if watched 80%
                elif time_pos > 30:
                    save_resume_time(show_id, current_ep, time_pos)

                if result == "QUIT" or result == "EOF":
                    if auto_scrobbled and resolveTracking(get_search_prev(), args, cfg):
                        tkn = cfg.get("anilist_token")
                        if tkn:
                            show_ctx = get_ui_show()
                            progress_ep = episode_progress_number(current_ep, current_ep_index + 1)
                            new_status = tracking_status_for_progress(show_ctx, progress_ep)
                            queued = queue_anilist_progress(
                                tkn, show_title, progress_ep, al_id,
                                show_ctx, ttype, new_status,
                                on_success=lambda ep=current_ep, ctx=show_ctx:
                                    set_action_feedback(ctx, f"AniList synced: EP {ep} watched."),
                                on_failure=lambda ctx=show_ctx:
                                    set_action_feedback(ctx, "Saved locally, but AniList sync is pending."),
                            )
                            if queued:
                                set_action_feedback(show_ctx, f"AniList sync queued: EP {current_ep}.")

                    if result == "EOF" and (args.binge or cfg.get("binge")):
                        if current_ep_index + 1 < total_eps:
                            next_ep = episode_id_at(
                                episode_ids, current_ep_index + 1
                            )
                            if is_incognito():
                                pending_osd_msg = None
                            elif auto_scrobbled:
                                pending_osd_msg = marked_watched_osd(
                                    current_ep,
                                    resolveTracking(
                                        get_search_prev(), args, cfg
                                    )
                                )
                            else:
                                progress_ep = episode_progress_number(
                                    current_ep, current_ep_index + 1
                                )
                                save_pending_completion(
                                    show_id, current_ep, progress_ep,
                                    next_ep, time_pos, duration
                                )
                                if time_pos > 0:
                                    save_resume_time(
                                        show_id, current_ep, time_pos
                                    )
                                pending_osd_msg = pending_completion_osd(
                                    current_ep, next_ep
                                )
                            current_ep_index += 1; current_ep = episode_id_at(episode_ids, current_ep_index); selected_stream = None; _clear_streams()
                            state = "PLAY"
                        else:
                            _ipc_player.quit()
                            print(f"\n{GREEN}Finished the last episode.{RESET}")
                            state = "QUIT"
                    else:
                        _ipc_player.quit()
                        state = "ACTION_MENU"

                elif result == "NEXT":
                    if current_ep_index + 1 < total_eps:
                        next_ep = episode_id_at(episode_ids, current_ep_index + 1)
                        if is_incognito():
                            pending_osd_msg = None
                        elif auto_scrobbled and resolveTracking(get_search_prev(), args, cfg):
                            tkn = cfg.get("anilist_token")
                            if tkn:
                                show_ctx = get_ui_show()
                                progress_ep = episode_progress_number(current_ep, current_ep_index + 1)
                                new_status = tracking_status_for_progress(show_ctx, progress_ep)
                                queued = queue_anilist_progress(
                                    tkn, show_title, progress_ep, al_id,
                                    show_ctx, ttype, new_status,
                                    on_success=lambda ep=current_ep, ctx=show_ctx:
                                        set_action_feedback(ctx, f"AniList synced: EP {ep} watched."),
                                    on_failure=lambda ctx=show_ctx:
                                        set_action_feedback(ctx, "Saved locally, but AniList sync is pending."),
                                )
                                pending_osd_msg = (
                                    sync_queued_osd(current_ep)
                                    if queued else marked_watched_osd(current_ep, False)
                                )
                        elif not auto_scrobbled:
                            progress_ep = episode_progress_number(current_ep, current_ep_index + 1)
                            save_pending_completion(show_id, current_ep, progress_ep, next_ep, time_pos, duration)
                            if time_pos > 0:
                                save_resume_time(show_id, current_ep, time_pos)
                            pending_osd_msg = pending_completion_osd(current_ep, next_ep)
                        current_ep_index += 1; current_ep = next_ep; selected_stream = None; _clear_streams()
                        state = "PLAY"
                    else:
                        _ipc_player.quit()
                        print(f"\n{GREEN}Finished the last episode.{RESET}")
                        state = "QUIT"
                elif result == "PREV":
                    if current_ep_index > 0:
                        current_ep_index -= 1; current_ep = episode_id_at(episode_ids, current_ep_index); selected_stream = None; _clear_streams()
                        state = "PLAY"
                    else:
                        _ipc_player.quit()
                        state = "ACTION_MENU"
                else:
                    _ipc_player.quit()
                    state = "ACTION_MENU"

        # ── ACTION MENU ───────────────────────────────────────────────────
        elif state == "ACTION_MENU":
            opts, acts = [], []
            is_tracking = resolveTracking(get_search_prev(), args, cfg)
            action_show = get_ui_show()
            episode_ids = ensure_episode_ids(action_show, ttype)
            if not episode_ids:
                err(episode_catalog_error(action_show))
                state = "DETAILS"
                continue
            total_eps = len(episode_ids) or total_eps
            current_ep_index = episode_index_for_id(episode_ids, current_ep)
            if current_ep_index is None:
                err(f"EP {current_ep} is not present in the provider catalog.")
                state = "EPISODE"
                continue
            next_ep = episode_id_at(episode_ids, current_ep_index + 1) if current_ep_index + 1 < total_eps else None
            prev_ep = episode_id_at(episode_ids, current_ep_index - 1) if current_ep_index > 0 else None
            if not is_incognito():
                if next_ep is not None:
                    opts.append("Mark & Play Next"); acts.append("TRACK_NEXT")
                opts.append("Mark as Watched"); acts.append("TRACK_ONLY")
            if next_ep is not None: opts.append("Next");    acts.append("NEXT")
            if prev_ep is not None: opts.append("Previous"); acts.append("PREV")
            if total_eps > 1: opts.append("Episodes"); acts.append("EPISODES")
            opts += ["Replay","Change Stream","Back","Quit"]
            acts += ["REPLAY","MIRRORS","BACK","QUIT"]

            # Inline hints for action menu
            action_hints = {}
            sync_txt = "save + sync" if is_tracking else "save local"

            for opt, act in zip(opts, acts):
                if act == "TRACK_ONLY": action_hints[opt] = f"{sync_txt} EP {current_ep}"
                elif act == "TRACK_NEXT": action_hints[opt] = f"{sync_txt} EP {current_ep}; play EP {next_ep}"
                elif act == "NEXT":     action_hints[opt] = f"play EP {next_ep}"
                elif act == "PREV":   action_hints[opt] = f"play EP {prev_ep}"
                elif act == "EPISODES": action_hints[opt] = "choose episode"
                elif act == "REPLAY": action_hints[opt] = f"replay EP {current_ep}"
                elif act == "MIRRORS":action_hints[opt] = "choose stream"
                elif act == "BACK":   action_hints[opt] = "Back"
                elif act == "QUIT":   action_hints[opt] = "Quit"

                        # Build action header with title + mirror status
            def _action_hdr(si):
                C_T  = "\033[1;97m"
                C_D  = "\033[38;5;248m"
                C_K  = "\033[38;5;244m"
                R    = "\033[0m"
                try:
                    w = os.get_terminal_size().columns
                except OSError:
                    w = 80
                n = _stream_count()
                with _bg_lock:
                    bg_alive = _bg_thread and _bg_thread.is_alive()
                    r, f = _bg_stats["resolved"], _bg_stats["failed"]
                    tot = _bg_stats.get('total', r+f)
                if bg_alive:
                    mstat = f"{C_D}✔ {n} streams found • checking mirrors ({r+f}/{tot}){R}"
                elif n > 0:
                    mstat = f"{C_D}✔ {n} streams ready • {tot}/{tot} mirrors checked{R}"
                else:
                    mstat = ""
                parts = []
                show = get_ui_show()
                tt = get_ui_ttype()

                feedback_time = show.get("_action_feedback_time", 0)
                has_feedback = (time.time() - float(feedback_time)) < 3.0 if feedback_time else False
                feedback_msg = show.get("_action_feedback", "")

                if show:
                    ep_str = f"EP {current_ep}/{total_eps}"
                    build_info_panel(show, tt, w, parts, override_ep_str=ep_str)
                    if has_feedback and len(parts) >= 4:
                        parts[3] = f"\033[32m✔ {feedback_msg}\033[0m"
                    elif mstat and len(parts) >= 4:
                        parts[3] = mstat

                _t = lambda s: _truncate_display(s, max(1, w - 1))
                if has_feedback:
                    parts.append(f"{C_K}{_t(feedback_msg)}{R}")
                else:
                    parts.append(f"{C_K}{_t('Enter/Right=select  ? = Help  Left/Esc=back')}{R}")


                return "\n".join(parts)
            hd7 = picker_help("Select action", "Go back", "Go back")
            idx = tui_pick("Select action", opts,
                           header_fn=_action_hdr,
                           hints=action_hints,
                           help_dict=hd7)
            if idx in (-2, -3):
                state = get_action_prev()
            else:
                a = acts[idx]
                if a == "TRACK_ONLY":
                    tkn = cfg.get("anilist_token")
                    synced = False
                    show_ctx = get_ui_show()
                    if tkn and resolveTracking(get_search_prev(), args, cfg, show_ctx):
                        progress_ep = episode_progress_number(current_ep, current_ep_index + 1)
                        synced = with_loading(
                            f"Saving locally and syncing AniList: EP {current_ep}…",
                            save_and_sync_watched,
                            show_ctx, current_ep, ttype,
                            tkn, show_title, progress_ep, al_id
                        )
                        if not synced:
                            set_action_feedback(show_ctx, "Saved locally, but AniList sync failed.")
                        else:
                            set_action_feedback(show_ctx, f"Saved locally and synced AniList: EP {current_ep} watched.")
                    else:
                        with_loading(
                            f"Saving EP {current_ep} locally…",
                            save_history, show_ctx, current_ep, ttype
                        )
                        set_action_feedback(show_ctx, f"Marked EP {current_ep} as watched locally.")
                    save_resume_time(show_id, current_ep, 0)
                    state = "ACTION_MENU"
                elif a == "TRACK_NEXT":
                    tkn = cfg.get("anilist_token")
                    synced = False
                    show_ctx = get_ui_show()
                    if tkn and resolveTracking(get_search_prev(), args, cfg, show_ctx):
                        progress_ep = episode_progress_number(current_ep, current_ep_index + 1)
                        synced = with_loading(
                            f"Saving locally and syncing AniList: EP {current_ep}…",
                            save_and_sync_watched,
                            show_ctx, current_ep, ttype,
                            tkn, show_title, progress_ep, al_id
                        )
                        if not synced:
                            set_action_feedback(show_ctx, "Saved locally, but AniList sync failed.")
                        else:
                            set_action_feedback(show_ctx, f"Saved locally and synced AniList: EP {current_ep} watched.")
                    else:
                        with_loading(
                            f"Saving EP {current_ep} locally…",
                            save_history, show_ctx, current_ep, ttype
                        )
                        set_action_feedback(show_ctx, f"Marked EP {current_ep} as watched locally.")
                    save_resume_time(show_id, current_ep, 0)
                    pending_osd_msg = marked_watched_osd(current_ep, synced)
                    current_ep_index += 1; current_ep = episode_id_at(episode_ids, current_ep_index); selected_stream=None; _clear_streams(); state="PLAY"
                elif a=="NEXT":
                    # Manual skip from action menu - do not auto-scrobble
                    current_ep_index += 1; current_ep = episode_id_at(episode_ids, current_ep_index); selected_stream=None; _clear_streams(); state="PLAY"
                elif a=="PREV":
                    current_ep_index -= 1; current_ep = episode_id_at(episode_ids, current_ep_index); selected_stream=None; _clear_streams(); state="PLAY"
                elif a=="EPISODES":
                    set_navigation_context(ep_prev="ACTION_MENU")
                    state="EPISODE"
                elif a=="REPLAY":
                    # Replay with same stream — don't reset selected_stream.
                    # But DO reset first_source_name so bg doesn't restart
                    # (already running or already done).
                    state="PLAY"
                elif a=="MIRRORS":
                    state="MIRRORS"
                elif a=="BACK":
                    state = get_action_prev()
                elif a=="QUIT":
                    state="QUIT"

        # ── MIRRORS ───────────────────────────────────────────────────────
        elif state == "MIRRORS":
            def _mlabel(s):
                tag = " ✓" if s.get("android_safe") else ""
                pref = get_preferred_mirror(show_id)
                is_pref = pref.get("source_name") == s["source_name"] and pref.get("resolution") == s.get("resolution", "?")
                if selected_stream and s.get("link") == selected_stream.get("link"):
                    prefix = "▶ "
                elif is_pref:
                    prefix = "★ "
                else:
                    prefix = ""
                raw = (f"{prefix}{s['source_name']} "
                       f"[{s.get('type','?').upper()}{tag}] "
                       f"{s.get('resolution','?')}")
                return re.sub(r'\s+', ' ', raw).strip()

            def _dedup():
                seen, out = set(), []
                for s in sorted(_stream_snapshot(), key=lambda x: x.get("source_priority",4)):
                    if s["link"] not in seen:
                        seen.add(s["link"]); out.append(s)
                return out

            _live_deduped = []

            def _mirror_refresh(q=""):
                nonlocal _live_deduped
                _live_deduped = _dedup()
                mopts = [_mlabel(s) for s in _live_deduped]
                with _bg_lock:
                    alive = _bg_thread and _bg_thread.is_alive()
                    r, f = _bg_stats["resolved"], _bg_stats["failed"]
                    tot = _bg_stats.get('total', r+f)
                C_T  = "\033[1;97m"
                C_D  = "\033[38;5;248m"
                C_K  = "\033[38;5;244m"
                R    = "\033[0m"
                try:
                    w = os.get_terminal_size().columns
                except OSError:
                    w = 80
                if alive:
                    plain_status = f"✔ {len(mopts)} streams found • checking mirrors ({r+f}/{tot})"
                else:
                    plain_status = f"✔ {len(mopts)} streams ready • {tot}/{tot} mirrors checked"
                parts = []
                show = get_ui_show()
                tt = get_ui_ttype()

                if show:
                    ep_str = f"EP {current_ep}/{total_eps}"
                    build_info_panel(show, tt, w, parts, override_ep_str=ep_str)
                toast = globals().get("_pref_toast")
                toast_time = globals().get("_pref_toast_time", 0)

                footer = lambda s: _truncate_display(s, max(1, w - 1))

                if toast and time.time() - toast_time < 3:
                    parts.append(f"\033[38;5;220m* {footer(toast)}\033[0m")
                else:
                    parts.append(f"{C_D}{footer(f'{plain_status}  │  ? = Help  Esc=back')}{R}")


                hdr = "\n".join(parts)
                return mopts, hdr, not alive

            init_opts, init_hdr, _ = _mirror_refresh()
            if not init_opts:
                with _bg_lock:
                    still_alive = _bg_thread and _bg_thread.is_alive()
                if not still_alive:
                    print(f"{RED}No mirrors found.{RESET}")
                    state="ACTION_MENU"
                    continue

            def _tab_pref(opt_idx):
                if 0 <= opt_idx < len(_live_deduped):
                    s = _live_deduped[opt_idx]
                    toggle_preferred_mirror(show_id, s["source_name"], s.get("resolution", "?"))
                    globals()["_pref_toast"] = "Preferred server updated (Will apply on next playback)"
                    globals()["_pref_toast_time"] = time.time()
                return _mirror_refresh()[:2]

            hd8 = picker_help("Play stream", "Go back", "Go back", "Mark preferred")
            globals()["_pref_toast"] = ""
            midx = tui_pick("Select mirror", init_opts, header=init_hdr,
                            live_fn=_mirror_refresh, tab_fn=_tab_pref, help_dict=hd8)
            if midx in (-2, -3): state="ACTION_MENU"
            elif midx >= 0 and midx < len(_live_deduped):
                selected_stream = _live_deduped[midx]
                state="PLAY"
            else:
                state="ACTION_MENU"


    else:
        _ipc_player.quit()
