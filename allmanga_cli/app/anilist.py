"""
AniList menu and browse handlers for allmanga-cli.
"""

from __future__ import annotations
from allmanga_cli import app_core
from allmanga_cli.ui.picker import tui_pick

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..context import CliFlags, UiState, MachineState

from ..domain.episodes import episode_id_at, episode_index_for_id
from ..domain.titles import get_show_display_title
from ..domain.airing import (
    airing_rows,
    airing_tab_label,
    next_airing_tab,
    previous_airing_tab,
)
from ..domain.sorting import (
    anilist_sort_label,
    next_anilist_sort_mode,
    normalize_anilist_sort_mode,
    previous_anilist_sort_mode,
    sort_anilist_shows,
)
from ..ui.help import picker_help, search_input_help
from ..ui.anilist_menu import (
    LIST_STATUSES as ANILIST_LIST_STATUSES,
    menu_header as anilist_menu_header,
    menu_navigation as anilist_menu_navigation,
)
from ..ui.picker_render import loading_frame as _loading_frame
from ..core.terminal import fit_terminal_line as _fit_terminal_line
from ..core.terminal import sanitize_terminal_text as _sanitize_terminal_text
from ..core.terminal import truncate_display as _truncate_display

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
_C_HINT = "\033[38;5;244m"
_RST    = "\033[0m"

ANILIST_LIST_LABELS = {
    None: "All",
    "CURRENT": "Watching",
    "WATCHING": "Watching",
    "PLANNING": "Planning",
    "PLAN_TO_WATCH": "Planning",
    "COMPLETED": "Completed",
    "PAUSED": "Paused",
    "DROPPED": "Dropped",
    "REPEATING": "Rewatching",
    "REWATCHING": "Rewatching",
}


def _footer_parts(*parts):
    return " | ".join(str(part) for part in parts if part)


def _anilist_badges(flags, args):
    badges = []
    if getattr(flags, "incognito_mode", False):
        badges.append("Incognito")
    if getattr(flags, "incognito_mode", False) or getattr(args, "no_sync", False):
        badges.append("Sync Off")
    return badges


def _anilist_list_label(status):
    if status is None:
        return ANILIST_LIST_LABELS[None]
    normalized = str(status or "").upper().replace(" ", "_").replace("-", "_")
    return ANILIST_LIST_LABELS.get(normalized, "Browse")


def handle_anilist_menu_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    valid_statuses = ANILIST_LIST_STATUSES
    if args.anilist and args.anilist.lower() != "menu":
        req_stat = args.anilist.upper()
        stat_map = {
            "WATCHING": "CURRENT", "PLANNING": "PLANNING",
            "COMPLETED": "COMPLETED", "REWATCHING": "REPEATING",
            "PAUSED": "PAUSED", "DROPPED": "DROPPED",
            "ALL": None, "AIRING": "ANILIST_AIRING",
            "CURRENT": "CURRENT", "REPEATING": "REPEATING"
        }
        mapped = stat_map.get(req_stat, "INVALID")
        if mapped == "INVALID":
            app_core.err(f"Invalid AniList status: {req_stat}")
            return "QUIT"
        ui.anilist_browse_status = mapped
        args.anilist = "menu"
        return "ANILIST_BROWSE"

    opts = list(valid_statuses.keys())

    def _menu_hdr(si):
        return anilist_menu_header()

    idx = tui_pick(
        flags, ui,
        "AniList Lists", opts,
        header_fn=_menu_hdr,
        help_dict=picker_help("Open list", "Search AllAnime", "Quit")
    )

    navigation = anilist_menu_navigation(idx)
    if navigation:
        if navigation == "SEARCH":
            ms.query_str = ""
        return navigation

    stat_val = valid_statuses[opts[idx]]
    if stat_val == "ANILIST_SEARCH":
        ms.query_str = ""
        ms.anilist_search_parent = "ANILIST_MENU"
        return "ANILIST_SEARCH"
    if stat_val == "ANILIST_AIRING":
        return "ANILIST_AIRING"

    ui.anilist_browse_status = stat_val
    return "ANILIST_BROWSE"


def _load_anilist_airing_shows(token, *, force_refresh=False):
    return app_core.with_anilist_menu_loading(
        "ANILIST_AIRING",
        "Loading AniList airing schedule...",
        app_core.fetch_anilist_list,
        token,
        None,
        force_refresh,
    )


def _open_anilist_show_from_picker(
    flags,
    ui,
    ms,
    args,
    ttype,
    source_show,
    parent_state,
):
    matched = app_core.with_loading(
        "Matching title on AllAnime...",
        app_core.match_anilist_show_to_allanime,
        source_show,
        ttype,
    )

    if not matched:
        matched = app_core._run_manual_match_search(flags, ui, source_show, ttype)
    if not matched:
        return parent_state

    ms.shows = [matched]
    ui.ui_show_ctx = matched
    ui.ui_ttype_ctx = ttype

    ms.show_id = matched["_id"]
    ms.show_title = get_show_display_title(matched)
    ms.total_eps = matched.get("availableEpisodes", {}).get(ttype, 0)

    episode_ids = app_core.load_episode_ids_for_selection(matched, ttype)
    ms.total_eps = len(episode_ids) or ms.total_eps

    if args.episode:
        ms.current_ep = str(args.episode)
        ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep)
        args.episode = None
        if not episode_ids:
            app_core.err(app_core.episode_catalog_error(matched))
            return "DETAILS"
        if ms.current_ep_index is None:
            app_core.err(f"EP {ms.current_ep} is not available from this provider.")
            return "EPISODE"
        ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
        return "PLAY"

    ui.search_prev_state = parent_state
    ui.ep_prev_state = parent_state
    ui.action_prev_state = parent_state
    ms.just_picked_anime = True
    return "DETAILS"


def handle_anilist_airing_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    base_shows = _load_anilist_airing_shows(cfg["anilist_token"], force_refresh=True)
    tab = getattr(ui, "anilist_airing_tab", "today")
    rows = airing_rows(base_shows, tab)
    row_shows = [show for show, _label in rows]
    shows = [show for show in row_shows if show]
    opts = [label for _show, label in rows]
    disabled_rows = {
        index for index, show in enumerate(row_shows)
        if show is None
    }

    def _rebuild(new_tab=None):
        nonlocal tab, rows, row_shows, shows, opts, disabled_rows
        if new_tab:
            tab = new_tab
            ui.anilist_airing_tab = tab
        rows = airing_rows(base_shows, tab)
        row_shows = [show for show, _label in rows]
        shows = [show for show in row_shows if show]
        opts = [label for _show, label in rows]
        disabled_rows = {
            index for index, show in enumerate(row_shows)
            if show is None
        }
        return opts, _airing_hdr(0), disabled_rows

    def _airing_top_hdr(si):
        show = row_shows[si] if 0 <= si < len(row_shows) else None
        if show:
            ui.hovered_show_id = show.get("_id")
            ui.hovered_show_obj = show
            app_core._hovered_show_id = ui.hovered_show_id
            poster = app_core._get_poster(show)
            if poster:
                return poster
        return ""

    def _airing_hdr(si):
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        parts = []
        selected_show = row_shows[si] if 0 <= si < len(row_shows) and row_shows[si] else {}
        if selected_show:
            app_core.build_info_panel(selected_show, ttype, w, parts)
        else:
            parts.extend([
                "",
                _fit_terminal_line(f"{_C_HINT}No airing episodes in {airing_tab_label(tab)}.{_RST}", w),
                _fit_terminal_line(f"{_C_HINT}Use Tab/Ctrl+N to switch tabs or Ctrl+R to refresh.{_RST}", w),
            ])
        footer_text = _footer_parts(
            f"{len(shows)} airing",
            *_anilist_badges(flags, args),
            "Enter/Right open",
            "Tab/Ctrl+N next tab",
            "Shift+Tab/Ctrl+P prev tab",
            "Ctrl+R refresh",
            "Esc back",
        )
        parts.append(app_core._poster_footer_line(
            selected_show,
            footer_text,
            w,
        ))
        return "\n".join(parts)

    def _airing_tab(_selected=None, direction=1):
        return _rebuild(
            previous_airing_tab(tab) if direction < 0 else next_airing_tab(tab)
        )

    def _airing_refresh(_selected=None):
        nonlocal base_shows
        base_shows = app_core.with_footer_loading(
            "Refreshing AniList airing schedule...",
            app_core.fetch_anilist_list,
            cfg["anilist_token"],
            None,
            True,
        )
        return _rebuild(tab)

    idx = tui_pick(
        flags,
        ui,
        lambda: f"AniList Airing · {airing_tab_label(tab)}",
        opts,
        header_fn=_airing_hdr,
        top_header_fn=_airing_top_hdr,
        tab_fn=_airing_tab,
        reverse_fn=_airing_refresh,
        count_total=lambda: len(shows),
        disabled_indices=disabled_rows,
        reverse_items=False,
        help_dict=picker_help(
            "Open title",
            "Back to lists",
            "Back to lists",
            "Next tab",
            "Previous tab",
            reverse_label="Refresh schedule",
        ),
    )
    if idx in (-2, -3):
        app_core._clear_poster_downloads()
        app_core.clear_terminal_images()
        return "ANILIST_MENU"
    if idx < 0:
        return "ANILIST_AIRING"
    selected = row_shows[idx] if 0 <= idx < len(row_shows) else None
    if not selected:
        return "ANILIST_AIRING"
    return _open_anilist_show_from_picker(
        flags, ui, ms, args, ttype, selected, "ANILIST_AIRING"
    )


def handle_anilist_browse_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    stat = ui.anilist_browse_status
    al_base_shows = app_core.load_anilist_browse(cfg["anilist_token"], stat)
    if not al_base_shows:
        app_core.err("No anime found in this AniList list.")
        return "ANILIST_MENU"

    sort_mode = normalize_anilist_sort_mode(cfg.get("anilist_sort", "recent"))
    sort_reverse = bool(cfg.get("anilist_sort_reverse", False))
    history_for_sort = app_core.load_history()
    al_shows = sort_anilist_shows(al_base_shows, sort_mode, history_for_sort)
    if sort_reverse:
        al_shows.reverse()
    opts = [f"{s['name']}" for s in al_shows]

    def _al_top_hdr(si):
        if 0 <= si < len(al_shows):
            ui.hovered_show_id = al_shows[si].get("_id")
            ui.hovered_show_obj = al_shows[si]
            app_core._hovered_show_id = ui.hovered_show_id
            poster = app_core._get_poster(al_shows[si])
            if poster: return poster
        return ""

    def _al_hdr(si):
        try: w = os.get_terminal_size().columns
        except OSError: w = 80
        parts = []
        selected_show = {}
        if 0 <= si < len(al_shows):
            s = al_shows[si]
            app_core.build_info_panel(s, ttype, w, parts, hide_anilist_status=stat)
            selected_show = s

        parts.append(app_core._poster_footer_line(
            selected_show,
            _footer_parts(
                f"{len(al_shows)} results",
                *_anilist_badges(flags, args),
                "Enter/Right open",
                "Tab/Ctrl+N next sort",
                "Shift+Tab/Ctrl+P prev sort",
                "Ctrl+R reverse",
                "Esc back",
            ),
            w
        ))
        return "\n".join(parts)

    def _al_tab(_selected=None, direction=1):
        nonlocal sort_mode, al_shows, opts
        if direction < 0:
            sort_mode = previous_anilist_sort_mode(sort_mode)
        else:
            sort_mode = next_anilist_sort_mode(sort_mode)
        cfg["anilist_sort"] = sort_mode
        app_core.save_config(cfg)
        al_shows = sort_anilist_shows(al_base_shows, sort_mode, history_for_sort)
        if sort_reverse:
            al_shows.reverse()
        opts = [f"{show['name']}" for show in al_shows]
        return opts, _al_hdr(0)

    def _al_reverse(_selected=None):
        nonlocal sort_reverse, al_shows, opts
        sort_reverse = not sort_reverse
        cfg["anilist_sort_reverse"] = sort_reverse
        app_core.save_config(cfg)
        al_shows.reverse()
        opts = [f"{show['name']}" for show in al_shows]
        return opts, _al_hdr(0)

    list_title = _anilist_list_label(stat)
    idx = tui_pick(
        flags, ui,
        lambda: f"AniList - {list_title} · {anilist_sort_label(sort_mode, sort_reverse)}",
        opts,
        header_fn=_al_hdr,
        top_header_fn=_al_top_hdr,
        tab_fn=_al_tab,
        reverse_fn=_al_reverse,
        help_dict=picker_help(
            "Open title",
            "Back to lists",
            "Back to lists",
            "Next sort",
            "Previous sort",
            reverse_label="Reverse order",
        ),
    )

    if idx in (-2, -3):
        return "ANILIST_MENU"
    if idx < 0:
        return "ANILIST_BROWSE"

    s = al_shows[idx]
    matched = app_core.with_loading(
        "Matching title on AllAnime...",
        app_core.match_anilist_show_to_allanime,
        s,
        ttype,
    )

    if matched:
        ms.shows = [matched]
        ui.ui_show_ctx = matched
        ui.ui_ttype_ctx = ttype

        ms.show_id = matched["_id"]
        ms.show_title = get_show_display_title(matched)
        ms.total_eps = matched.get("availableEpisodes", {}).get(ttype, 0)

        episode_ids = app_core.load_episode_ids_for_selection(matched, ttype)
        ms.total_eps = len(episode_ids) or ms.total_eps

        if args.episode:
            ms.current_ep = str(args.episode)
            ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep)
            args.episode = None
            if not episode_ids:
                app_core.err(app_core.episode_catalog_error(matched))
                return "DETAILS"
            elif ms.current_ep_index is None:
                app_core.err(f"EP {ms.current_ep} is not available from this provider.")
                return "EPISODE"
            else:
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
                return "PLAY"
        else:
            ui.search_prev_state = "ANILIST_BROWSE"
            ui.ep_prev_state = "ANILIST_BROWSE"
            ui.action_prev_state = "ANILIST_BROWSE"
            ms.just_picked_anime = True
            return "DETAILS"
    else:
        matched = app_core._run_manual_match_search(flags, ui, s, ttype)
        if matched:
            ms.shows = [matched]
            ui.ui_show_ctx = matched
            ui.ui_ttype_ctx = ttype

            ms.show_id = matched["_id"]
            ms.show_title = get_show_display_title(matched)
            ms.total_eps = matched.get("availableEpisodes", {}).get(ttype, 0)

            episode_ids = app_core.ensure_episode_ids(matched, ttype)
            ms.total_eps = len(episode_ids) or ms.total_eps
            ms.current_ep_index = 0
            ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)

            ui.search_prev_state = "ANILIST_BROWSE"
            ui.ep_prev_state = "ANILIST_BROWSE"
            ui.action_prev_state = "ANILIST_BROWSE"
            ms.just_picked_anime = True
            return "DETAILS"

    return "ANILIST_BROWSE"


def handle_anilist_search_state(
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

    def _search_input_header(provider_name, esc_action="quit"):
        def _hdr(si):
            C_K = "\033[38;5;244m"
            R = "\033[0m"
            parts = [""]
            parts.append(f"{C_K}Use Up/Down to browse previous searches.{R}")
            parts.append(f"\033[38;5;250mSource: \033[1;97m{provider_name}\033[0m")
            if ui.search_error:
                parts.append(f"{C_K}{ui.search_error}  │  Esc={esc_action}{R}")
            else:
                parts.append(f"{C_K}Enter=search  ? = Help  Esc={esc_action}{R}")
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

    def _search_result_header(provider_name, base_query, ttype_local, get_results_fn, get_loading_fn, esc_action="quit"):
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
                parts.append(f"{C_K}Use Up/Down to browse previous searches.{R}")
                parts.append(f"\033[38;5;250mSource: \033[1;97m{provider_name}\033[0m")
            elif shows and 0 <= si < len(shows):
                selected_show = shows[si]
                app_core.build_info_panel(selected_show, ttype_local, w, parts)
            else:
                selected_show = {}
                parts.append("")
                if shows and filter_query:
                    parts.append(f"{C_K}No match: {_truncate_display(filter_query, max(1, w - 11))}{R}")
                else:
                    parts.append("")
                parts.append(f"\033[38;5;250mSource: \033[1;97m{provider_name}\033[0m")
            if loading_msg:
                parts.append(loading_msg)
            elif shows:
                footer = _footer_parts(
                    f'{len(shows)} result(s) for "{safe_query}"',
                    *_anilist_badges(flags, args),
                    "Enter=select",
                    "?=Help",
                    "Left=search",
                    f"Esc={esc_action}",
                )
                parts.append(app_core._poster_footer_line(selected_show, footer, w))
            else:
                parts.append(f'{C_K}No results for "{safe_query}"  │  Left=new search  Esc={esc_action}{R}')
            return "\n".join(parts)
        return _hdr

    # Step 1: Input Page
    if not ms.query_str:
        esc_action = "back" if ms.anilist_search_parent != "QUIT" else "quit"
        res = tui_pick(
            flags, ui,
            "Search Anime", [],
            header_fn=_search_input_header("AniList", esc_action),
            return_query_on_enter=True,
            query_history=app_core.load_search_history(),
            is_search=True,
            help_dict=search_input_help(
                "Back" if ms.anilist_search_parent != "QUIT" else "Quit"
            ),
        )
        ui.search_error = ""
        if res == -2:
            return ms.anilist_search_parent
        if not res:
            return "ANILIST_SEARCH"
        ms.query_str = str(res).strip()
        ms.just_searched = True
        app_core.save_search_history(ms.query_str)

    if not ms.query_str:
        app_core.err("Search query cannot be empty.")
        return "QUIT"

    # Step 2: Fetch Results ONCE
    live_fn, get_results, get_loading, get_error = app_core._cached_search_results(
        ms.query_str,
        "_last_al_query_str",
        "_last_al_shows",
        lambda: app_core.make_anilist_oneshot_search(cfg.get("anilist_token"), ms.query_str)
    )

    # Step 3: Title Selection Page
    app_core.enter_alt_screen()

    initial_opts = [f"{s.get('name', 'Unknown')}" for s in get_results()]
    esc_action = "back" if ms.anilist_search_parent != "QUIT" else "quit"

    if len(initial_opts) == 1:
        idx = 0
    else:
        hd4 = picker_help(
            "Select anime",
            "New search",
            "Back" if ms.anilist_search_parent != "QUIT" else "Quit",
        )
        idx = tui_pick(
            flags, ui,
            "Search Anime", initial_opts,
            header_fn=_search_result_header(
                "AniList", ms.query_str, ttype, get_results, get_loading,
                esc_action
            ),
            top_header_fn=_search_cover_header(get_results),
            live_fn=live_fn,
            is_search=False,
            help_dict=hd4,
            auto_select_single_when_done=ms.just_searched,
        )

    shows = get_results()
    ms.shows = shows
    ms.last_al_query_str = ms.query_str
    ms.last_al_shows = shows

    if idx == -2:
        return ms.anilist_search_parent
    elif idx == -3:
        ms.query_str = ""
        return "ANILIST_SEARCH"
    elif idx == -4:
        ui.search_error = get_error() or f'No results found for "{ms.query_str}"'
        ms.query_str = ""
        return "ANILIST_SEARCH"
    elif isinstance(idx, str):
        if idx.strip():
            ms.query_str = idx.strip()
        return "ANILIST_SEARCH"
    else:
        s = shows[idx]
        matched = app_core.with_loading(
            "Matching title on AllAnime...",
            app_core.match_anilist_show_to_allanime,
            s,
            ttype,
        )

        if matched:
            ui.ui_show_ctx = matched
            ui.ui_ttype_ctx = ttype

            ms.total_eps = matched.get("availableEpisodes", {}).get(ttype, 0)
            ms.show_id = matched.get("_id")
            ms.show_title = get_show_display_title(matched)

            episode_ids = app_core.load_episode_ids_for_selection(matched, ttype)
            ms.total_eps = len(episode_ids) or ms.total_eps

            try:
                al_progress = max(0, int(matched.get("_anilist_progress") or 0))
            except (TypeError, ValueError):
                al_progress = 0
            current_label = (
                app_core.episode_id_for_progress(matched, ttype, al_progress)
                if al_progress > 0 else None
            )
            current_idx = episode_index_for_id(episode_ids, current_label) if current_label else None
            if current_idx is not None and current_idx + 1 < len(episode_ids):
                ms.current_ep = episode_id_at(episode_ids, current_idx + 1)
            elif current_idx is not None:
                ms.current_ep = episode_id_at(episode_ids, current_idx)
            else:
                ms.current_ep = episode_id_at(episode_ids, 0)

            ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep)
            if episode_ids and ms.current_ep_index is not None:
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            elif episode_ids:
                ms.current_ep_index = 0
                ms.current_ep = episode_id_at(episode_ids, 0)

            ui.search_prev_state = "ANILIST_SEARCH"
            ui.ep_prev_state = "ANILIST_SEARCH"
            ui.action_prev_state = "ANILIST_SEARCH"
            ms.just_picked_anime = True
            return "DETAILS"
        else:
            matched = app_core._run_manual_match_search(flags, ui, s, ttype)
            if matched:
                ui.ui_show_ctx = matched
                ui.ui_ttype_ctx = ttype

                ms.total_eps = matched.get("availableEpisodes", {}).get(ttype, 0)
                ms.show_id = matched.get("_id")
                ms.show_title = get_show_display_title(matched)

                episode_ids = app_core.load_episode_ids_for_selection(matched, ttype)
                ms.total_eps = len(episode_ids) or ms.total_eps
                ms.current_ep_index = 0
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)

                ui.search_prev_state = "ANILIST_SEARCH"
                ui.ep_prev_state = "ANILIST_SEARCH"
                ui.action_prev_state = "ANILIST_SEARCH"
                ms.just_picked_anime = True
                return "DETAILS"

    return "ANILIST_SEARCH"
