"""
Search and History state handlers for allmanga-cli.
"""

from __future__ import annotations
from allmanga_cli import app_core
from allmanga_cli.ui.picker import tui_pick

import os
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..context import CliFlags, UiState, MachineState

from ..domain.episodes import episode_id_at, episode_index_for_id
from ..domain.titles import get_show_display_title
from ..ui.help import picker_help, search_input_help
from ..ui import picker as _picker_mod
from ..ui.spinner import spinner_frame, spinner_from_config
from ..ui.picker_render import loading_frame as _loading_frame
from ..core.terminal import fit_terminal_line as _fit_terminal_line
from ..core.terminal import sanitize_terminal_text as _sanitize_terminal_text
from ..core.terminal import truncate_display as _truncate_display


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
_C_HINT = "\033[38;5;244m"
_RST    = "\033[0m"
YELLOW  = "\033[1;33m"


def _footer_parts(*parts):
    return " | ".join(str(part) for part in parts if part)


def _session_badges(flags, args, *, search_context=False):
    badges = []
    if getattr(flags, "incognito_mode", False):
        badges.append("\033[38;2;155;125;185mINCOGNITO\033[0m")
    if search_context and getattr(args, "sync", False) and not getattr(args, "no_sync", False):
        badges.append("Sync On")
    return badges


# ---------------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------------
history_refresh_status = {}
def handle_history_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    hist = app_core.load_history()
    if not hist:
        app_core.warn("Watch history is empty.")
        return "QUIT"

    history_modes = ["Active", "Up to date", "Completed", "All"]
    history_mode = ui.history_filter
    if history_mode not in history_modes:
        history_mode = "Active"

    filtered_hist = app_core.filter_history_entries(hist, history_mode)
    hopts = [app_core.format_history_entry(h) for h in filtered_hist]

    def _rebuild_history_view():
        nonlocal filtered_hist, hopts
        filtered_hist = app_core.filter_history_entries(hist, history_mode)
        hopts = [app_core.format_history_entry(entry) for entry in filtered_hist]

    _history_open_time = time.time()
    history_refresh_status["BATCH"] = "Checking for new episodes..."
    def _batch_refresh_worker():
        try:
            if app_core.refresh_history_anilist_airing_batch(hist):
                _rebuild_history_view()
            for entry in hist:
                s_obj = entry.get("show", {})
                s_id = str(s_obj.get("_id") or "")
                if s_id and (
                    app_core.get_show_anilist_id(s_obj)
                    or s_obj.get("_anilist_airing_checked_at", 0) >= _history_open_time
                ):
                    _refreshed_history_ids.add(s_id)
        finally:
            history_refresh_status.pop("BATCH", None)
            _picker_mod._needs_redraw = True

    threading.Thread(target=_batch_refresh_worker, daemon=True).start()

    _hover_index = -1
    _hover_start_time = time.time()
    _refreshed_history_ids = set()
    _in_flight_hover_refresh = set()

    def _trigger_hover_refresh_if_needed():
        if not (0 <= _hover_index < len(filtered_hist)):
            return
        entry = filtered_hist[_hover_index]
        show = entry.get("show", {})
        show_id = str(show.get("_id") or "")
        if not show_id or show_id in _refreshed_history_ids or show_id in _in_flight_hover_refresh:
            return

        # AniList-backed titles are already handled by the AniList batch check
        if app_core.get_show_anilist_id(show):
            _refreshed_history_ids.add(show_id)
            return

        # Finished titles with known episode counts don't have new episodes to check
        status = str(show.get("status") or "").upper()
        if status in ("FINISHED", "COMPLETED", "ENDED") and show.get("episodeCount"):
            _refreshed_history_ids.add(show_id)
            return

        if (
            show.get("_episode_catalog_state") == "loaded"
            or show.get("_anilist_airing_checked_at", 0) >= _history_open_time
            or show.get("_allanime_checked_at", 0) >= _history_open_time
        ):
            _refreshed_history_ids.add(show_id)
            return

        _in_flight_hover_refresh.add(show_id)
        history_refresh_status["SINGLE"] = "Checking for new episodes..."
        _picker_mod._needs_redraw = True

        def _worker():
            try:
                changed = app_core.refresh_history_entry_allanime_catalog(entry)
                _refreshed_history_ids.add(show_id)
                show["_episode_catalog_state"] = "loaded"
                if changed:
                    app_core.patch_history_entry_show(show_id, entry.get("translation_type", "sub"), show)
                    _rebuild_history_view()
            finally:
                _in_flight_hover_refresh.discard(show_id)
                history_refresh_status.pop("SINGLE", None)
                _picker_mod._needs_redraw = True

        threading.Thread(target=_worker, daemon=True).start()

    def _history_footer(entry, width):
        updated = app_core.format_history_updated_time(entry)
        default = _footer_parts(
            f"Updated {updated}" if updated else "",
            "Enter/Right open",
            "Left search",
            "Tab/Ctrl+N next",
            "Shift+Tab/Ctrl+P prev",
            "Del/Ctrl+D delete",
            "Esc quit",
        )
        return app_core._poster_footer_line(entry.get("show", {}), default, width)

    def _hist_top_hdr(si):
        if 0 <= si < len(filtered_hist):
            show = filtered_hist[si].get("show", {})
            ui.hovered_show_id = show.get("_id")
            ui.hovered_show_obj = show
            app_core._hovered_show_id = ui.hovered_show_id
            poster = app_core._get_poster(show)
            if poster:
                return poster
        return ""

    def _hist_hdr(si):
        nonlocal _hover_index, _hover_start_time
        if si != _hover_index:
            _hover_index = si
            _hover_start_time = time.time()

        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        parts = []
        selected_show = {}
        if not filtered_hist:
            if history_mode == "Active":
                msg = "No active history entries."
            elif history_mode == "Up to date":
                msg = "No up-to-date titles."
            elif history_mode == "Completed":
                msg = "No completed titles."
            else:
                msg = "Watch history is empty."
            parts.append(f"\033[38;5;244m{msg}\033[0m")
        elif 0 <= si < len(filtered_hist):
            h = filtered_hist[si]
            tt = h.get("translation_type", "sub")
            selected_show = h.get("show", {})
            app_core.build_info_panel(selected_show, tt, w, parts, local_only=True, main_title=selected_show.get('name'))
        selected_entry = (
            filtered_hist[si]
            if 0 <= si < len(filtered_hist)
            else {}
        )

        status_msg = history_refresh_status.get("BATCH") or history_refresh_status.get("SINGLE")

        if status_msg:
            spinner = spinner_frame(spinner_from_config(cfg))
            parts.append(f"\033[36m{spinner} {status_msg}\033[0m")
        else:
            parts.append(_history_footer(selected_entry, w))

        return "\n".join(parts)


    def _hist_delete(si):
        nonlocal hist, filtered_hist, hopts
        if 0 <= si < len(filtered_hist):
            h = filtered_hist[si]
            show = h.get("show", {})
            if app_core.delete_history_entry(show.get("_id"), h.get("translation_type", "sub")):
                hist = app_core.load_history()
                filtered_hist = app_core.filter_history_entries(hist, history_mode)
                hopts = [app_core.format_history_entry(x) for x in filtered_hist]
        return hopts, _hist_hdr(0)

    def _set_history_mode(next_index):
        nonlocal history_mode, filtered_hist, hopts
        history_mode = history_modes[next_index % len(history_modes)]
        ui.history_filter = history_mode
        filtered_hist = app_core.filter_history_entries(hist, history_mode)
        hopts = [app_core.format_history_entry(entry) for entry in filtered_hist]
        return hopts, _hist_hdr(0)

    def _hist_tab(_selected=None, direction=1):
        mode_index = history_modes.index(history_mode)
        return _set_history_mode(mode_index + direction)

    def _hist_tick():
        now = time.time()
        if _hover_index >= 0 and (now - _hover_start_time) >= 1.2:
            _trigger_hover_refresh_if_needed()
        return (
            history_refresh_status.get("BATCH") is not None
            or bool(_in_flight_hover_refresh)
        )

    hidx = tui_pick(
        flags, ui,
        lambda: f"Watch History · {history_mode}", hopts,
        header_fn=_hist_hdr,
        top_header_fn=_hist_top_hdr,
        tab_fn=_hist_tab,
        delete_fn=_hist_delete,
        live_fn=lambda _query: (list(hopts), "", False),
        info_fn=app_core.make_info_fn(lambda: [e.get("show", {}) for e in filtered_hist], ui),
        help_dict=picker_help(
            "Open details",
            "Search",
            "Quit",
            "Next filter",
            "Previous filter",
            "Remove from history",
        ),
        keep_cursor_hidden_on_select=True,
        count_total=lambda: len(hist),
        tick_fn=_hist_tick
    )
    if hidx == -2:
        return "QUIT"
    if hidx == -3:
        return "SEARCH"
    if hidx >= 0:
        h = filtered_hist[hidx]
        show = h.get("show", {})
        ttype_hist = h.get("translation_type", "sub")
        app_core.prepare_show_display_state(show, ttype_hist)
        ms.show_id = show.get("_id")
        ms.show_title = get_show_display_title(show)
        ms.total_eps = show.get("availableEpisodes", {}).get(ttype_hist, 1)
        ms.current_ep = app_core.playback_ep_from_history_entry(h, ttype_hist)

        # Only fetch fresh if catalog is not already loaded/refreshed in this instance
        is_fresh = (
            show.get("_episode_catalog_state") == "loaded"
            or str(show.get("_id") or "") in _refreshed_history_ids
            or show.get("_anilist_airing_checked_at", 0) >= _history_open_time
            or show.get("_allanime_checked_at", 0) >= _history_open_time
        )
        if not is_fresh:
            episode_ids = app_core.load_episode_ids_for_selection(show, ttype_hist)
        else:
            episode_ids = app_core.ensure_episode_ids(show, ttype_hist)

        ms.total_eps = len(episode_ids) or ms.total_eps
        ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep, labels=show.get("_episode_labels"))
        if episode_ids and ms.current_ep_index is not None:
            ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
        elif episode_ids:
            ms.current_ep_index = 0
            ms.current_ep = episode_id_at(episode_ids, 0)

        ui.ui_show_ctx = show
        ui.ui_ttype_ctx = ttype_hist
        ms.just_picked_anime = True
        app_core.set_navigation_context(ui, search_prev="HISTORY", ep_prev="HISTORY", action_prev="HISTORY")
        return "DETAILS"

    return "HISTORY"


# ---------------------------------------------------------------------------
# SEARCH
# ---------------------------------------------------------------------------
def handle_search_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    ui.ui_show_ctx = {}
    ms.ep_cache_key = None
    ms.ep_cache_data = None
    app_core._clear_poster_downloads()
    provider_id = app_core.provider_key(getattr(args, "provider", "allanime"))
    provider_name = app_core.provider_display_name(provider_id)
    
    # Determine category: Anime, Donghua, Movies/Shows
    category = "Anime"
    try:
        from ..providers import get_provider_registry
        registry = get_provider_registry()
        meta = registry.get(provider_id, {})
        ptype = (meta.get("type") or "").lower()
        if ptype == "donghua":
            category = "Donghua"
        elif ptype in ("movie", "movies"):
            category = "Movies/Shows"
    except Exception:
        category = "Anime"

    search_title = f"Search {category}"

    def _search_input_header(provider_name, esc_action="quit"):
        def _hdr(si):
            C_K = "\033[38;5;244m"
            R = "\033[0m"
            parts = [""]
            if flags.incognito_mode:
                parts.append(f"{C_K}Search & watch history is paused.{R}")
            else:
                parts.append(f"{C_K}Use Up/Down to browse previous searches.{R}")
            if provider_name:
                parts.append(f"{C_K}Provider: {provider_name}{R}")
            nav = f"Enter=search  ? = Help  Esc={esc_action}"
            if flags.incognito_mode:
                nav = f"\033[38;2;155;125;185mINCOGNITO\033[0m | {nav}"
            if ui.search_error:
                parts.append(f"{C_K}{ui.search_error}  │  Esc={esc_action}{R}")
            else:
                parts.append(f"{C_K}{nav}{R}")
            return "\n".join(parts)
        return _hdr

    def _search_cover_header(get_results_fn):
        def _hdr(si):
            shows_local = get_results_fn()
            if shows_local and 0 <= si < len(shows_local):
                ui.hovered_show_id = shows_local[si].get("_id") or shows_local[si].get("id")
                ui.hovered_show_obj = shows_local[si]
                app_core._hovered_show_id = ui.hovered_show_id
                poster = app_core._get_poster(shows_local[si])
                if poster:
                    return poster
            return ""
        return _hdr

    def _search_result_header(provider_name, base_query, ttype_local, get_results_fn, get_loading_fn, esc_action="quit", get_error_fn=None):
        def _hdr(si):
            C_K = "\033[38;5;244m"
            R = "\033[0m"
            try:
                w = os.get_terminal_size().columns
            except OSError:
                w = 80
            parts = []
            safe_query = _sanitize_terminal_text(base_query)
            filter_query = _sanitize_terminal_text(ui.active_picker_query or "")
            shows = get_results_fn()
            loading_msg = get_loading_fn()
            if loading_msg:
                selected_show = {}
                parts.append("")
                if flags.incognito_mode:
                    parts.append(f"{C_K}Search & watch history is paused.{R}")
                else:
                    parts.append(f"{C_K}Use Up/Down to browse previous searches.{R}")
                if provider_name:
                    parts.append(f"{C_K}Provider: {provider_name}{R}")
            elif shows and 0 <= si < len(shows):
                selected_show = shows[si]
                app_core.build_info_panel(selected_show, ttype_local, w, parts, main_title=selected_show.get('name'))
            else:
                selected_show = {}
                parts.append("")
                if shows and filter_query:
                    parts.append(f"{C_K}No match: {_truncate_display(filter_query, max(1, w - 11))}{R}")
                else:
                    parts.append("")
            if loading_msg:
                parts.append(loading_msg)
            elif shows:
                footer = _footer_parts(
                    f'"{safe_query}"',
                    provider_name,
                    *_session_badges(flags, args, search_context=True),
                    "Enter=select",
                    "?=Help",
                    "Left=search",
                    f"Esc={esc_action}",
                )
                parts.append(app_core._poster_footer_line(selected_show, footer, w))
            else:
                err_msg = get_error_fn() if get_error_fn else ""
                if err_msg:
                    parts.append(f'\033[38;5;196m{err_msg}{R}  │  Left=new search  Esc={esc_action}')
                else:
                    parts.append(f'{C_K}No results for "{safe_query}"  │  Left=new search  Esc={esc_action}{R}')
            return "\n".join(parts)
        return _hdr

    # Step 1: Input Page
    if not ms.query_str:
        hd1 = search_input_help("Quit")
        q_history = [] if flags.incognito_mode else app_core.load_search_history()
        res = tui_pick(
            flags, ui,
            search_title, [],
            header_fn=_search_input_header(provider_name),
            return_query_on_enter=True,
            query_history=q_history,
            delete_fn=app_core.delete_search_history_entry if not flags.incognito_mode else None,
            is_search=True,
            help_dict=hd1
        )
        ui.search_error = ""
        if res == -2:
            return "QUIT"
        if not res:
            return "SEARCH"
        ms.query_str = str(res).strip()
        ms.just_searched = True
        if not flags.incognito_mode and ms.query_str:
            app_core.save_search_history(ms.query_str)
    else:
        if not flags.incognito_mode and ms.query_str:
            app_core.save_search_history(ms.query_str)

    if not ms.query_str:
        app_core.err("Search query cannot be empty.")
        return "QUIT"

    # Step 2: Fetch Results ONCE
    live_fn, get_results, get_loading, get_error = app_core._cached_search_results(
        ms.query_str,
        f"_last_{provider_id}_query_str",
        f"_last_{provider_id}_shows",
        lambda: app_core.make_provider_oneshot_search(
            ms.query_str,
            ttype,
            provider_id,
        )
    )

    # Step 3: Title Selection Page
    app_core.enter_alt_screen()

    initial_opts = [f"{s.get('name', 'Unknown')}" for s in get_results()]
    if len(initial_opts) == 1:
        idx = 0
    else:
        hd2 = picker_help("Select anime", "New search", "Quit")
        idx = tui_pick(
            flags, ui,
            search_title, initial_opts,
            header_fn=_search_result_header(provider_name, ms.query_str, ttype, get_results, get_loading, get_error_fn=get_error),
            top_header_fn=_search_cover_header(get_results),
            live_fn=live_fn,
            initial_query=ms.query_str,
            is_search=False,
            help_dict=hd2,
            auto_select_single_when_done=ms.just_searched,
            info_fn=app_core.make_info_fn(get_results, ui),
        )

    shows = get_results()
    # Replace global mutations by mutating MachineState
    ms.shows = shows
    ms.last_aa_query_str = ms.query_str
    ms.last_aa_shows = shows

    if idx == -2:
        return "QUIT"
    elif idx == -3:
        ms.query_str = ""
        return "SEARCH"
    elif idx == -4:
        ui.search_error = (
            get_error() or f'No results found for "{ms.query_str}"'
        )
        ms.query_str = ""
        return "SEARCH"
    elif isinstance(idx, str):
        if idx.strip():
            ms.query_str = idx.strip()
        return "SEARCH"
    else:
        s = shows[idx]
        if args.sync and not args.no_sync and cfg.get("anilist_token"):
            matched = app_core.with_loading(
                "Matching title on AniList...",
                app_core.match_allanime_show_to_anilist,
                flags,
                ui,
                s,
                cfg["anilist_token"],
                False,
            )
            if not matched:
                matched = app_core._run_manual_anilist_match(
                    flags, ui, s, cfg["anilist_token"]
                )
            if matched:
                s = matched

        ms.show_id = s["_id"]
        sync_enabled = bool(args.sync and not args.no_sync and app_core.get_show_anilist_id(s))
        ms.show_title = get_show_display_title(s, sync_enabled=sync_enabled)
        ms.total_eps = s.get("availableEpisodes", {}).get(ttype, 0)
        episode_ids = app_core.load_episode_ids_for_selection(s, ttype)
        ms.total_eps = len(episode_ids) or ms.total_eps

        ui.ui_show_ctx = s
        ui.ui_ttype_ctx = ttype
        ms.just_picked_anime = True
        app_core.set_navigation_context(ui, search_prev="SEARCH", ep_prev="SEARCH", action_prev="SEARCH")

        requested_episode_missing = False
        if args.episode:
            requested_ep = str(args.episode)
            requested_idx = episode_index_for_id(
                episode_ids, requested_ep, labels=s.get("_episode_labels")
            )
            args.episode = None
            if requested_idx is not None:
                ms.current_ep_index = requested_idx
                ms.current_ep = episode_id_at(episode_ids, requested_idx)
                ms.selected_stream = None
                app_core._clear_streams()
                return "PLAY"

            if episode_ids:
                app_core.set_action_feedback(
                    s,
                    f"EP {requested_ep} is not available • Choose an episode",
                )
            else:
                app_core.set_action_feedback(s, app_core.episode_catalog_error(s))
            ms.current_ep_index = 0
            ms.current_ep = episode_id_at(episode_ids, 0) if episode_ids else requested_ep
            requested_episode_missing = True
        elif (h := app_core.get_history_entry(s, ttype)):
            ms.current_ep = app_core.playback_ep_from_history_entry(h, ttype)
        else:
            ms.current_ep = episode_id_at(episode_ids, 0)

        ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep)

        if episode_ids and ms.current_ep_index is not None:
            ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
        elif episode_ids:
            ms.current_ep_index = 0
            ms.current_ep = episode_id_at(episode_ids, 0)
        else:
            app_core.set_action_feedback(s, app_core.episode_catalog_error(s))
            return "DETAILS"

        if requested_episode_missing:
            return "EPISODE"

        return "DETAILS"
