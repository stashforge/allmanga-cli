"""Sub-modals for details screen: updating progress, status, and scores."""

from __future__ import annotations

import os
from typing import Any

from ..context import CliFlags, UiState, MachineState
from ..domain.episodes import highest_episode_number
from ..domain.tracking import (
    tracking_status_for_progress,
    apply_tracking_progress_local,
    completed_media_total,
)
from ..ui.help import picker_help
from ..ui.picker import tui_pick
from .. import app_core


def handle_update_progress_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,
) -> str:
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
    sync_active = bool(al_id and has_token and resolve_tracking_fn(ui.search_prev_state, args, cfg, s))


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
                "Syncing to AniList…",
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
                app_core.set_action_feedback(s, f"✔ Synced EP {next_progress} to AniList")
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
            app_core.set_action_feedback(s, f"✔ Saved progress: EP {next_progress}")

    return "DETAILS"


def handle_update_status_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,
) -> str:
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
                "Updating status…",
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
                        f"✔ Synced status to AniList"
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
    resolve_tracking_fn,
) -> str:
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
                "Updating score…",
                app_core.update_anilist_entry,
                cfg["anilist_token"],
                int(al_id),
                score=int(opts[idx]) * 10,
                show=s,
            )
            if not updated:
                app_core.err(f"Could not update AniList score to {opts[idx]}/10.")

    return "DETAILS"
