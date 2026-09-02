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
    highest_episode_number,
    is_contiguous_legacy_catalog as _is_contiguous_legacy_catalog,
    normalize_episode_ids as _normalize_episode_ids,
)
from allmanga_cli.domain import history as history_domain
from allmanga_cli.domain import reconciliation as reconciliation_domain
from allmanga_cli.core.storage import find_offline_file_for_episode

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

from allmanga_cli.ui.player_screen import _player_ui_state, add_status_line as _add_status


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

from allmanga_cli.context import (
    set_ui_context,
    get_ui_show,
    get_ui_ttype,
    set_navigation_context,
    get_search_prev,
    get_ep_prev,
    get_action_prev,
)


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


from allmanga_cli.ui.info_panel import (
    buildEpStr,
    buildYearStr,
    buildInfoMetadataLine,
    build_info_panel,
)

should_update_anilist_progress = anilist.should_update_anilist_progress
sync_progress_and_checkpoint = anilist.sync_progress_and_checkpoint
sync_watched_to_anilist = anilist.sync_watched_to_anilist
save_and_sync_watched = anilist.save_and_sync_watched

from allmanga_cli.state.preferences import (
    ACTION_FEEDBACK_DURATION,
    set_action_feedback,
    get_active_feedback,
)



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

from allmanga_cli.core.anilist import load_anilist_browse
from allmanga_cli.core.enrichment import enrich_show_if_missing



from allmanga_cli.ui.info_panel import (
    make_info_fn,
    make_shows_info_fn,
    make_single_show_info_fn,
)



from allmanga_cli.playback.engine import (
    _exit_player_screen,
    _get_player_poster,
    _playback_episode_summary,
)






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

from allmanga_cli.domain.metadata import (
    prepare_show_display_state,
    batch_prepare_shows_display_state,
)

get_resume_time = storage.get_resume_time
load_resume_time = storage.get_resume_time
save_resume_time = storage.save_resume_time

get_pending_completion = storage.get_pending_completion
save_pending_completion = storage.save_pending_completion
clear_pending_completion = storage.clear_pending_completion
get_al_match = storage.get_al_match
save_al_match = storage.save_al_match
get_source_anilist_match = storage.get_source_anilist_match
save_source_anilist_match = storage.save_source_anilist_match

from allmanga_cli.domain.history import (
    playback_ep_from_history_entry,
    refresh_history_entry_provider_catalog,
    refresh_history_entry_allanime_catalog,
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

from allmanga_cli.domain.metadata import apply_provider_metadata_to_history_show
apply_allanime_metadata_to_history_show = apply_provider_metadata_to_history_show



refresh_history_anilist_airing_batch = anilist.refresh_history_anilist_airing_batch

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

from allmanga_cli.media.urls import (
    provider_frontend_domain,
    provider_episode_url,
    allanime_frontend_domain,
    allanime_episode_url,
    open_external_url,
    redact_sensitive_text,
)

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
    provider_catalog_refresh_fn=lambda entry: refresh_history_entry_provider_catalog(entry),
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

from allmanga_cli.app.search_coordinator import (
    _provider_search_cache,
    make_provider_oneshot_search,
    make_allanime_oneshot_search,
    make_anilist_oneshot_search,
    _cached_search_results,
    _remember_search_results,
)

from allmanga_cli.providers import provider_display_name

from allmanga_cli.ui.modals import (
    search_input_header as _search_input_header,
    search_cover_header as _search_cover_header,
    search_result_header as _search_result_header,
    manual_match_input_header as _manual_match_input_header,
    manual_anilist_input_header as _manual_anilist_input_header,
    select_provider_for_match as _select_provider_for_match,
    confirm_auto_match as _confirm_auto_match,
    confirm_auto_anilist_match as _confirm_auto_anilist_match,
    no_match_prompt as _no_match_prompt,
)








from allmanga_cli.domain.matching import (
    _find_fuzzy_anilist_candidate,
    _run_anilist_match_search,
    _run_manual_anilist_match,
    _run_manual_match_search,
    match_provider_show_to_anilist,
    match_allanime_show_to_anilist,
)



from allmanga_cli.core.processes import is_termux, check_deps


from allmanga_cli.domain.matching import (
    extract_franchise_query,
    extract_matching_queries,
    choose_confident_match as _choose_confident_match,
    best_provider_match as _best_allanime_match,
    match_anilist_show_to_provider,
    match_anilist_show_to_allanime,
)


# ── API ───────────────────────────────────────────────────────────────────────
from allmanga_cli.services.catalog import (
    _current_provider,
    _allanime_provider,
    _provider_for_title,
    search_anime,
    get_show_by_id,
    get_allanime_show,
    fetch_episode_catalog,
    fetch_episode_ids,
    update_available_count_from_episode_ids,
    ensure_episode_ids,
    check_translation_switch_capability,
    episode_catalog_needs_fetch,
    load_episode_ids_for_selection,
    episode_catalog_error,
    get_episode_data,
    get_clock_links,
)



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
_prune_dead_stream = streams._prune_dead_stream
_get_cached_ep_data = streams._get_cached_ep_data
_set_cached_ep_data = streams._set_cached_ep_data
_publish_stream = streams._publish_stream
_generation_is_current = streams._generation_is_current
_update_bg_stats = streams._update_bg_stats
start_bg_resolve = streams.start_bg_resolve
from allmanga_cli.media.sources import ping_stream_liveness, is_stream_valid_fast

from allmanga_cli.playback.engine import (
    _redraw_player,
    _ipc_player,
    play_desktop,
    play_local_video,
)




# ── Main ──────────────────────────────────────────────────────────────────────

fetch_episode_stream = streams.fetch_episode_stream

from allmanga_cli.app.orchestrator import (
    main,
    handle_config_command,
    trigger_migration,
)
from allmanga_cli.core.processes import (
    _active_subprocesses,
    register_subprocess,
    unregister_subprocess,
    kill_active_subprocesses,
)

