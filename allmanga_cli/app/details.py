"""
Details and Update state handlers for allmanga-cli.
"""

from __future__ import annotations
import os
import decimal
from typing import TYPE_CHECKING, Any
from allmanga_cli import app_core
from allmanga_cli.ui.picker import tui_pick

if TYPE_CHECKING:
    from ..context import CliFlags, UiState, MachineState

from ..domain.episodes import episode_id_at, episode_index_for_id, episode_progress_number, detect_next_episode_gap, highest_episode_number
from ..domain.titles import get_show_display_title
from ..domain.tracking import (
    tracking_status_for_progress,
    apply_tracking_progress_local,
    completed_media_total,
)
from ..ui.help import picker_help
from ..playback.rules import should_clear_query_on_child_left
from ..core.terminal import fit_terminal_line as _fit_terminal_line

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
_C_HINT = "\033[38;5;244m"
_RST    = "\033[0m"


def handle_details_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    s = ui.ui_show_ctx
    ttype_local = ui.ui_ttype_ctx

    _just_entered = ms.just_picked_anime
    if _just_entered:
        if s.get("_id") and ui.search_prev_state in (
            "HISTORY", "SEARCH", "ANILIST_SEARCH", "ANILIST_BROWSE", "ANILIST_AIRING"
        ):
            if s.get("_episode_catalog_state") != "loaded":
                entry = {"show": s, "translation_type": ttype_local}
                app_core.with_loading(
                    "Fetching episode catalog...",
                    app_core.refresh_history_entry_allanime_catalog,
                    entry
                )
        ms.just_picked_anime = False

    episode_ids = app_core.ensure_episode_ids(s, ttype_local)
    ms.total_eps = len(episode_ids) or ms.total_eps

    if _just_entered and s.get("_id"):
        app_core.patch_history_entry_show(s.get("_id"), ttype_local, s)

    ms.current_ep_index = episode_index_for_id(
        episode_ids, ms.current_ep, labels=ui.ui_show_ctx.get("_episode_labels")
    )
    if ms.current_ep_index is None:
        ms.current_ep_index = 0
        if episode_ids:
            ms.current_ep = episode_id_at(episode_ids, 0)

    from_anilist_context = ui.search_prev_state in (
        "ANILIST_BROWSE", "ANILIST_SEARCH", "ANILIST_AIRING"
    )
    s["_anilist_context"] = from_anilist_context
    use_anilist = bool(resolve_tracking_fn(ui.search_prev_state, args, cfg, s) and app_core.get_show_anilist_id(s))

    has_token = bool(cfg.get("anilist_token")) and not flags.incognito_mode
    has_anilist_link = bool(app_core.get_show_anilist_id(s))

    should_use_anilist_data = has_token and has_anilist_link and (from_anilist_context or use_anilist)

    if should_use_anilist_data:
        media = app_core.with_loading(
            "Refreshing AniList entry…",
            app_core.fetch_anilist_media,
            cfg.get("anilist_token"),
            app_core.get_show_anilist_id(s),
        )
        if media:
            app_core.update_anime_from_anilist_media(s, media)

    if from_anilist_context:
        s.pop("_sync_conflict", None)
        s["_progress_authority"] = "AL"
    elif not use_anilist:
        s.pop("_sync_conflict", None)

    app_core.prepare_show_display_state(s, ttype_local, use_anilist)
    local_before = s.get("_local_progress")
    try:
        remote_before = int(s.get("_anilist_progress") or 0)
    except (TypeError, ValueError):
        remote_before = 0



    app_core.prepare_show_display_state(s, ttype_local, use_anilist)
    local_progress = s.get("_local_progress")
    try:
        al_progress = int(s.get("_anilist_progress") or 0)
    except (TypeError, ValueError):
        al_progress = 0

    def effective_playback_progress(show, local_prog, al_prog, from_anilist, use_al):
        if from_anilist or use_al:
            return al_prog, "AL"
        else:
            return int(local_prog) if local_prog is not None else 0, "LOCAL"

    prog, prog_source = effective_playback_progress(s, local_progress, al_progress, from_anilist_context, use_anilist)

    total = s.get("episodeCount")
    try: total = int(total) if total is not None else 0
    except ValueError: total = 0

    released = s.get("availableEpisodes", {}).get(ttype_local, 0)
    try: released = int(released) if released is not None else 0
    except ValueError: released = 0
    if episode_ids:
        _highest = highest_episode_number(episode_ids)
        try:
            _highest_num = int(decimal.Decimal(str(_highest)))
        except (decimal.InvalidOperation, ValueError, TypeError):
            _highest_num = len(episode_ids)
        released = max(released, _highest_num)

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
    isDesktop = player in ["mpv", "mpvrex"] and not app_core.is_termux()

    opts = []
    detail_play_ep = episode_id_at(episode_ids, 0) if episode_ids else None

    # Find next playable using _episode_ids position, not prog arithmetic
    if from_anilist_context or use_anilist:
        current_ep_label = app_core.episode_id_for_progress(s, ttype_local, al_progress) if al_progress > 0 else "0"
    else:
        current_ep_label = s.get("_local_episode_label") or "0"
    _current_idx = (
        episode_index_for_id(
            episode_ids, current_ep_label, labels=ui.ui_show_ctx.get("_episode_labels")
        )
        if episode_ids
        else None
    )
    if _current_idx is not None and _current_idx + 1 < len(episode_ids):
        detail_next_ep = episode_ids[_current_idx + 1]
    else:
        detail_next_ep = None

    has_gaps, gap_str = detect_next_episode_gap(current_ep_label, detail_next_ep)

    # For display totals, use episode labels only — never mix catalog index
    detail_max_ep_label = released

    # next_manual_progress: the episode label to mark when "Mark Next Watched"
    if detail_next_ep:
        next_manual_progress = episode_progress_number(detail_next_ep, 0)
    else:
        next_manual_progress = episode_progress_number(current_ep_label, 0) + 1


    try:
        current_num = decimal.Decimal(str(current_ep_label))
    except decimal.InvalidOperation:
        current_num = decimal.Decimal(0)

    from ..domain.episodes import parse_episode_label
    parsed = parse_episode_label(current_ep_label)
    al_prog = s.get("_anilist_progress", 0) if use_anilist else 0

    show_anilist_actions = has_token and has_anilist_link and (from_anilist_context or use_anilist)
    show_sync_toggle = False
    show_link_action = False


    if episode_ids and (playback_status == "COMPLETED" or (total and current_num >= total)):
        opts.append("Start Rewatch")
        if len(episode_ids) > 1 and isDesktop:
            opts.append("Binge from Start")
    elif episode_ids and prog == 0:
        opts.append("Play")
        if len(episode_ids) > 1 and isDesktop:
            opts.append("Binge")
    elif episode_ids and detail_next_ep is not None:
        opts.append("Play Next")
        if isDesktop:
            opts.append("Binge")
            if len(episode_ids) > 1:
                opts.append("Binge from Start")
    elif episode_ids and detail_next_ep is None and (current_ep_label == str(episode_ids[-1]) or (prog > 0 and prog >= len(episode_ids))):
        opts.append("Replay Latest")
        if len(episode_ids) > 1 and isDesktop:
            opts.append("Binge from Start")

    if episode_ids:
        opts.append("Episodes")
    elif not s.get("_action_feedback"):
        app_core.set_action_feedback(s, app_core.episode_catalog_error(s))

    if not getattr(ms, "_is_downloads", False):
        if from_anilist_context and has_anilist_link:
            opts.append("Change AllAnime Match")
        elif show_link_action and s.get("_id") and not has_anilist_link:
            opts.append("Link AniList")

    opts.append("Progress")
    if show_anilist_actions:
        opts.extend(["Status", "Rate"])

    opts.extend(["Back", "Quit"])

    al_status = str(s.get("_anilist_list") or "").title() or "None"
    al_score = s.get("_anilist_score")
    score_str = f"★ {al_score}" if al_score and float(al_score) > 0 else "not rated"

    local_p = app_core.get_local_progress(s, ttype_local)
    local_p_str = f"local EP {local_p}" if local_p is not None else "local EP 0"
    if show_anilist_actions:
        prog_hint = f"{local_p_str} · AL EP {al_prog}"
    else:
        prog_hint = local_p_str

    def clean_ep_label(ep_id, fallback_idx=None):
        if not ep_id: return ""
        labels = s.get("_episode_labels", {})
        from allmanga_cli.domain.episodes import clean_episode_identifier
        if str(ep_id) in labels:
            return clean_episode_identifier(labels[str(ep_id)]) or clean_episode_identifier(str(ep_id)) or str(ep_id)
        cleaned = clean_episode_identifier(str(ep_id))
        if cleaned:
            return cleaned
        if fallback_idx is not None:
            return str(fallback_idx + 1)
        return str(ep_id)

    play_label = clean_ep_label(detail_play_ep, 0)
    next_label = clean_ep_label(detail_next_ep, (_current_idx + 1) if _current_idx is not None else None)
    replay_label = clean_ep_label(current_ep_label, len(episode_ids) - 1) if current_ep_label else (clean_ep_label(episode_ids[-1]) if episode_ids else "1")
    binge_label = next_label if 'Play Next' in opts else play_label

    hints = {
        "Play": f"EP {play_label}",
        "Play Next": f"EP {next_label} \u2022 {gap_str}" if gap_str else f"EP {next_label}",
        "Replay Latest": f"EP {replay_label}",
        "Binge": f"from EP {binge_label}",
        "Binge from Start": f"from EP {play_label}",
        "Start Rewatch": f"replay from EP {play_label}",
        "Episodes": "browse all",
        "Change AllAnime Match": "link a different streaming title",
        "Link AniList": "link a different tracking title",
        "Progress": prog_hint,
        "Status": al_status,
        "Rate": score_str,
        "Back": "return to previous screen",
        "Quit": "exit program"
    }

    def _details_hdr(si):
        try: w = os.get_terminal_size().columns
        except OSError: w = 80
        parts = []
        app_core.build_info_panel(s, ttype_local, w, parts, local_only=getattr(ms, "_is_downloads", False))
        direct_single = (
            ui.search_prev_state in ("SEARCH", "ANILIST_SEARCH")
            and len(ms.shows) <= 1
            and ms.just_searched
        )
        nav_text = "Left=search  Esc=quit" if direct_single else "Left/Esc=back"
        if direct_single and ui.search_prev_state == "ANILIST_SEARCH":
            nav_text = (
                "Left=search  Esc="
                + ("back" if ms.anilist_search_parent != "QUIT" else "quit")
            )
        full_nav_text = f"Enter/Right=select  ? = Help  {nav_text}"
        if has_gaps:
            full_nav_text = f"{len(episode_ids)} listed  {full_nav_text}"

        parts.append(app_core._poster_footer_line(s, full_nav_text, w))
        return "\n".join(parts)

    direct_single = (
        ui.search_prev_state in ("SEARCH", "ANILIST_SEARCH")
        and len(ms.shows) <= 1
        and ms.just_searched
    )

    hd5 = picker_help(
        "Select option",
        "New search" if direct_single else "Go back",
        (
            "Back"
            if direct_single
            and ui.search_prev_state == "ANILIST_SEARCH"
            and ms.anilist_search_parent != "QUIT"
            else "Quit"
        ) if direct_single else "Go back"
    )

    idx = tui_pick(
        flags, ui,
        f"Anime Details", opts,
        header_fn=_details_hdr,
        hints=hints,
        info_fn=app_core.make_single_show_info_fn(s, ui),
        help_dict=hd5
    )

    if idx == -2:
        previous = ui.search_prev_state
        if direct_single:
            ms.query_str = ""
            return (
                ms.anilist_search_parent
                if previous == "ANILIST_SEARCH"
                else "QUIT"
            )
        return previous

    if idx == -3:
        previous = ui.search_prev_state
        if should_clear_query_on_child_left(previous, direct_single):
            ms.query_str = ""
        return previous

    if idx >= 0:
        opt = opts[idx]
        if opt in ("Play", "Play Next", "Start Rewatch", "Replay Latest", "Binge", "Binge from Start"):
            if opt in ("Binge", "Binge from Start"):
                args.binge = True
            else:
                args.binge = False
            ui.action_prev_state = "DETAILS"

            if opt == "Play Next":
                if _current_idx is not None and _current_idx + 1 < len(episode_ids):
                    ms.current_ep_index = _current_idx + 1
                else:
                    ms.current_ep_index = min(max(int(prog), 0), max(0, ms.total_eps - 1))
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            elif opt == "Replay Latest":
                ms.current_ep_index = max(0, len(episode_ids) - 1)
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            elif opt == "Start Rewatch":
                if use_anilist:
                    reset_result = app_core.with_loading(
                        "Starting AniList rewatch…",
                        app_core._push_local_progress,
                        s, ttype_local, cfg.get("anilist_token"), 0
                    )
                    if reset_result.get("action") == "failed":
                        app_core.err("Could not start AniList rewatch.")
                        return "DETAILS"
                else:
                    app_core.write_history_progress(s, 0, ttype_local, touch=False)
                ms.current_ep_index = 0
                ms.current_ep = episode_id_at(episode_ids, 0)
            elif opt in ("Play", "Binge from Start"):
                ms.current_ep_index = 0
                ms.current_ep = episode_id_at(episode_ids, 0)
            elif opt == "Binge":
                if detail_next_ep is not None and _current_idx is not None and _current_idx + 1 < len(episode_ids):
                    ms.current_ep_index = _current_idx + 1
                else:
                    ms.current_ep_index = 0
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            else:
                ms.current_ep_index = 0
                ms.current_ep = episode_id_at(episode_ids, 0)

            ms.selected_stream = None
            app_core._clear_streams()
            return "PLAY"


        elif opt == "Episodes":
            ui.ep_prev_state = "DETAILS"
            return "EPISODE"

        elif opt == "Change AllAnime Match":
            al_show = {
                "_id": app_core.get_show_anilist_id(s),
                "name": s.get("_display_name") or s.get("name", ""),
                "englishName": s.get("_display_english_name") or s.get("englishName", ""),
                "_anilist_list": s.get("_anilist_list"),
                "_anilist_progress": s.get("_anilist_progress"),
                "_next_airing_ep": s.get("_next_airing_ep"),
                "_next_airing_time": s.get("_next_airing_time"),
                "_next_airing_at": s.get("_next_airing_at"),
                "thumbnail": s.get("thumbnail")
            }
            new_match = app_core._run_manual_match_search(flags, ui, al_show, ttype_local)
            if new_match:
                app_core.set_title_sync(new_match, use_anilist)
                app_core.prepare_show_display_state(new_match, ttype_local, use_anilist)
                ui.ui_show_ctx = new_match
                ui.ui_ttype_ctx = ttype_local

                ms.show_id = new_match.get("_id")
                ms.show_title = get_show_display_title(new_match)
                ms.total_eps = new_match.get("availableEpisodes", {}).get(ttype_local, 0)

                episode_ids = app_core.ensure_episode_ids(new_match, ttype_local)
                ms.total_eps = len(episode_ids) or ms.total_eps
                ms.current_ep_index = 0
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            return "DETAILS"

        elif opt == "Link AniList":
            matched = app_core._run_manual_anilist_match(flags, ui, s, cfg["anilist_token"])
            if matched:
                app_core.set_title_sync(s, True)
                app_core.prepare_show_display_state(s, ttype_local, True)
                ms.show_title = get_show_display_title(s, sync_enabled=True)
            return "DETAILS"

        elif opt == "Progress":
            return "UPDATE_PROGRESS"

        elif opt == "Status":
            return "UPDATE_STATUS"

        elif opt == "Rate":
            return "UPDATE_SCORE"

        elif opt == "Back":
            previous = ui.search_prev_state
            if direct_single:
                ms.query_str = ""
            return previous

        elif opt == "Quit":
            return "QUIT"

    return "DETAILS"


def handle_update_progress_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    s = ui.ui_show_ctx
    ttype_local = ui.ui_ttype_ctx
    episode_ids = app_core.ensure_episode_ids(s, ttype_local)

    local_p = app_core.get_local_progress(s, ttype_local)
    try:
        prog = int(s.get("_anilist_progress") or local_p or 0)
    except ValueError:
        prog = int(local_p or 0)

    released = s.get("availableEpisodes", {}).get(ttype_local, 0)
    try:
        released = int(released) if released is not None else 0
    except ValueError:
        released = 0
    if episode_ids:
        import decimal as _dec
        _highest = highest_episode_number(episode_ids)
        try:
            _highest_num = int(_dec.Decimal(str(_highest)))
        except (_dec.InvalidOperation, ValueError, TypeError):
            _highest_num = len(episode_ids)
        released = max(released, _highest_num)

    max_progress = max(released, prog)
    if max_progress <= 0:
        max_progress = max(prog, 1)

    def _progress_hdr(si):
        try: w = os.get_terminal_size().columns
        except OSError: w = 80
        parts = []
        app_core.build_info_panel(s, ttype_local, w, parts, local_only=getattr(ms, "_is_downloads", False))
        parts.append(app_core._poster_footer_line(s, "Enter/Right=set progress  Ctrl+R=flip  ? = Help  Left/Esc=back", w))
        return "\n".join(parts)

    progress_order = list(range(max_progress, -1, -1))

    def _progress_label(p):
        label = f"{p}/{max_progress}"
        if p <= prog:
            return f"\033[38;5;244m{label}\033[0m"
        return label

    al_id = app_core.get_show_anilist_id(s)
    has_token = bool(cfg.get("anilist_token")) and not flags.incognito_mode
    sync_active = bool(al_id and has_token)

    progress_opts = [_progress_label(p) for p in progress_order]
    progress_hints = {}
    for p in progress_order:
        key = f"{p}/{max_progress}"
        if p == prog:
            progress_hints[key] = "current"
        elif p < prog:
            progress_hints[key] = "lower progress"
        else:
            progress_hints[key] = "sync to AniList" if sync_active else "mark watched"

    def _progress_tab_fn(opt=None):
        nonlocal progress_order, progress_opts
        progress_order.reverse()
        progress_opts = [_progress_label(p) for p in progress_order]
        return (progress_opts, _progress_hdr(0))

    hd9 = picker_help(
        "Set progress",
        "Go back",
        "Go back",
        "Flip order",
        reverse_label="Flip order",
    )
    picker_title = "Set AniList Progress" if sync_active else "Set Watch Progress"
    idx = tui_pick(
        flags, ui,
        picker_title, progress_opts,
        header_fn=_progress_hdr,
        hints=progress_hints,
        tab_fn=_progress_tab_fn,
        reverse_fn=_progress_tab_fn,
        info_fn=app_core.make_single_show_info_fn(s, ui),
        help_dict=hd9
    )

    if idx >= 0:
        next_progress = progress_order[idx]
        if sync_active:
            status_value = tracking_status_for_progress(s, next_progress) if next_progress > 0 else None
            updated = app_core.with_loading(
                f"Syncing AniList progress: EP {next_progress}…",
                app_core.update_anilist_entry,
                cfg["anilist_token"],
                int(al_id),
                progress=next_progress,
                status=status_value,
                show=s,
            )
            if updated:
                apply_tracking_progress_local(s, next_progress, status_value)
                s["_progress_authority"] = "AL"
                app_core.set_action_feedback(s, f"AniList synced: EP {next_progress} watched.")
            else:
                app_core.err("AniList sync failed.")
        else:
            if episode_ids and next_progress > 0:
                target_idx = min(next_progress - 1, len(episode_ids) - 1)
                target_ep = episode_ids[target_idx]
            else:
                target_ep = str(next_progress)
            app_core.write_history_progress(s, target_ep, ttype_local, touch=True)
            s["_local_progress"] = next_progress
            s["_local_episode_label"] = str(target_ep)
            s["_progress_authority"] = "LOCAL"
            app_core.set_action_feedback(s, f"Progress updated: EP {next_progress} watched.")

    return "DETAILS"


def handle_update_status_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    s = ui.ui_show_ctx
    ttype_local = ui.ui_ttype_ctx

    def _status_hdr(si):
        try: w = os.get_terminal_size().columns
        except OSError: w = 80
        parts = []
        app_core.build_info_panel(s, ttype_local, w, parts, local_only=getattr(ms, "_is_downloads", False))
        parts.append(app_core._poster_footer_line(s, "Enter/Right=select  ? = Help  Left/Esc=back", w))
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

    idx = tui_pick(
        flags, ui,
        "Update AniList Status", opts,
        header_fn=_status_hdr,
        info_fn=app_core.make_single_show_info_fn(s, ui),
        help_dict=hd7
    )

    if idx >= 0:
        al_id = app_core.get_show_anilist_id(s)
        if al_id:
            label, status_value = status_choices[idx]
            progress_value = None
            if status_value == "COMPLETED":
                progress_value = completed_media_total(s, ttype_local)
                if not progress_value:
                    app_core.err("This anime is not finished or its total EP count is unknown.")
                    return "DETAILS"

            updated = app_core.with_loading(
                f"Updating AniList status: {label}",
                app_core.update_anilist_entry,
                cfg["anilist_token"],
                int(al_id),
                progress=progress_value,
                status=status_value,
                show=s,
            )

            if updated:
                s["_anilist_list"] = status_value
                if progress_value is not None:
                    apply_tracking_progress_local(s, progress_value, status_value)
                    s["_progress_authority"] = "AL"
                    app_core.set_action_feedback(
                        s,
                        f"AniList completed: EP {progress_value} watched."
                    )
            else:
                app_core.err(f"Could not update AniList status to {label}.")

    return "DETAILS"


def handle_update_score_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    s = ui.ui_show_ctx
    ttype_local = ui.ui_ttype_ctx

    def _score_hdr(si):
        try: w = os.get_terminal_size().columns
        except OSError: w = 80
        parts = []
        app_core.build_info_panel(s, ttype_local, w, parts, local_only=getattr(ms, "_is_downloads", False))
        parts.append(app_core._poster_footer_line(s, "Enter/Right=select  ? = Help  Left/Esc=back", w))
        return "\n".join(parts)

    opts = [str(i) for i in range(10, 0, -1)]
    hd8 = picker_help("Select score", "Go back", "Go back")

    idx = tui_pick(
        flags, ui,
        "Update Score", opts,
        header_fn=_score_hdr,
        info_fn=app_core.make_single_show_info_fn(s, ui),
        help_dict=hd8
    )

    if idx >= 0:
        al_id = app_core.get_show_anilist_id(s)
        if al_id:
            updated = app_core.with_loading(
                f"Updating AniList score: {opts[idx]}/10",
                app_core.update_anilist_entry,
                cfg["anilist_token"],
                int(al_id),
                score=int(opts[idx]) * 10,
                show=s,
            )
            if not updated:
                app_core.err(f"Could not update AniList score to {opts[idx]}/10.")

    return "DETAILS"
