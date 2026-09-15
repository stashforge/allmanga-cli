"""Episode selection and label formatting handlers for playback."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..context import CliFlags, UiState, MachineState

from ..domain.episodes import (
    episode_id_at,
    episode_index_for_id,
    episode_label,
    clean_episode_identifier,
)
from ..playback.rules import should_clear_query_on_child_left
from ..ui.help import picker_help
from ..ui.picker import tui_pick
from ..core.terminal import truncate_display as _truncate_display
from .. import app_core

_C_HINT = "\033[38;5;244m"
_RST    = "\033[0m"


def _episode_labels_for(show: dict, ttype: str) -> dict:
    if not show:
        return {}
    labels = show.get("_episode_labels") or {}
    labels_ttype = show.get("_episode_labels_ttype")
    if labels_ttype and labels_ttype != ttype:
        return {}
    return labels


def _display_episode_label(show: dict, episode_id, ttype: str) -> str:
    labels = _episode_labels_for(show, ttype)
    raw = str(labels.get(str(episode_id)) or episode_id)
    from allmanga_cli.domain.episodes import resolve_dual_episode_label
    dual = resolve_dual_episode_label(show, raw)
    if dual:
        return dual
    return clean_episode_identifier(raw) or raw


def _fmt_ep(label):
    raw = str(label).strip()
    from allmanga_cli.domain.episodes import parse_episode_dual_numbers
    _, sec = parse_episode_dual_numbers(raw)
    clean = raw if sec else (clean_episode_identifier(raw) or raw)
    label_str = clean
    if not label_str:
        return "EP ?"
    if label_str[0].isdigit():
        return f"EP {label_str}"
    if label_str.lower() == "ova":
        return "OVA"
    if label_str.lower().startswith("ova "):
        return "OVA " + label_str[4:]
    return label_str.title()


def _clear_episode_source_state(ms: "MachineState") -> None:
    ms.ep_cache_key = None
    ms.ep_cache_data = None
    ms.selected_stream = None


def format_mirror_label(stream: dict, *, prefix: str = "", safe_tag: str = "") -> str:
    name = str(stream.get("source_name") or "Unknown")
    stream_type = str(stream.get("type") or "?").upper()
    resolution = str(stream.get("resolution") or "?")
    parts = [f"{prefix}{name}"]
    if f"[{stream_type}" not in name.upper():
        parts.append(f"[{stream_type}{safe_tag}]")
    elif safe_tag and "✓" not in name and "✔" not in name:
        parts.append(safe_tag.strip())

    if resolution != "?" and resolution.casefold() not in name.casefold():
        parts.append(resolution)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def handle_episode_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,
) -> str:
    show = ui.ui_show_ctx
    episode_ids = app_core.ensure_episode_ids(show, ttype)
    if not episode_ids and ttype in ("dub", "sub"):
        alt_ttype = "sub" if ttype == "dub" else "dub"
        alt_ids = app_core.ensure_episode_ids(show, alt_ttype)
        if alt_ids:
            p_name = (show.get("_provider_name") or (show.get("_provider") or "").title() or "provider") if show else "provider"
            missing_mode = ttype.upper()
            ttype = alt_ttype
            ui.ui_ttype_ctx = ttype
            episode_ids = alt_ids
            app_core.set_action_feedback(
                show,
                f"No {missing_mode} available for this title on {p_name}. Switched to {ttype.upper()}."
            )
    if not episode_ids:
        app_core.err(app_core.episode_catalog_error(show))
        if ui.ep_prev_state in ("SEARCH", "ANILIST_SEARCH", "ANILIST_BROWSE", "ANILIST_AIRING"):
            return "DETAILS"
        return ui.ep_prev_state

    ms.total_eps = len(episode_ids) or ms.total_eps
    episode_labels = _episode_labels_for(show, ttype)
    display_order = list(range(len(episode_ids)))
    if app_core.get_episode_order(ms.show_id, cfg.get("episode_order", "asc")) == "desc":
        display_order.reverse()

    def _is_ep_downloaded(eid, lbl):
        if not getattr(ms, "_is_downloads", False):
            return True
        dl_files = getattr(ms, "_download_files", {}) or {}
        if str(eid) in dl_files or str(lbl) in dl_files:
            return True
        from ..domain.episodes import clean_episode_identifier, parse_episode_dual_numbers
        prim, sec = parse_episode_dual_numbers(str(lbl))
        clean = (prim or clean_episode_identifier(str(lbl)) or str(lbl)).lstrip("0") or "0"
        clean_eid = clean_episode_identifier(str(eid))
        clean_eid_num = (clean_eid.lstrip("0") or "0") if clean_eid else None
        if clean in dl_files or (clean_eid_num and clean_eid_num in dl_files):
            return True
        for k in dl_files:
            kp, ks = parse_episode_dual_numbers(str(k))
            kc = (kp or clean_episode_identifier(str(k)) or str(k)).lstrip("0") or "0"
            if kc == clean or (clean_eid_num and kc == clean_eid_num) or (sec and sec == ks):
                return True
        f = app_core.find_offline_file_for_episode(ms.show_title or (show.get("name", "") if show else ""), lbl, cfg)
        if f:
            return True
        if prim:
            f = app_core.find_offline_file_for_episode(ms.show_title or (show.get("name", "") if show else ""), prim, cfg)
            if f:
                return True
        return False

    def _build_ep_option(eid):
        lbl = episode_label(eid, episode_labels)
        if getattr(ms, "_is_downloads", False) and not _is_ep_downloaded(eid, lbl):
            return f"\033[38;5;244m{lbl}\033[0m"
        return lbl

    def _compute_disabled_indices():
        if not getattr(ms, "_is_downloads", False):
            return set()
        dis = set()
        for opt_i, orig_i in enumerate(display_order):
            eid = episode_ids[orig_i]
            lbl = episode_label(eid, episode_labels)
            if not _is_ep_downloaded(eid, lbl):
                dis.add(opt_i)
        return dis

    ep_opts = [_build_ep_option(episode_ids[i]) for i in display_order]
    disabled_indices = _compute_disabled_indices()

    _hdr_cache: dict[tuple, str] = {}

    def _ep_hdr(si):
        try: w = os.get_terminal_size().columns
        except OSError: w = 80
        feedback = app_core.get_active_feedback(show)
        cache_key = (w, ttype, feedback, getattr(ms, "_is_downloads", False))
        if cache_key in _hdr_cache:
            return _hdr_cache[cache_key]
        parts = []
        if show:
            app_core.build_info_panel(show, ttype, w, parts, local_only=getattr(ms, "_is_downloads", False))

        _t = lambda s: _truncate_display(s, max(1, w - 1))
        direct_single = ui.ep_prev_state == "SEARCH" and len(ms.shows) <= 1 and ms.just_searched
        nav_text = "Esc=Search" if direct_single else "Esc=Back"
        if feedback:
            parts.append(f"\033[38;5;222m{_t(feedback)}{_RST}")
        else:
            p_name = (show.get("_provider_name") or (show.get("_provider") or "").title()) if show else ""
            prefix = f"{p_name} • " if p_name else ""
            parts.append(f"{_C_HINT}{_t(prefix + 'Tab=Sub/Dub • Ctrl+R=flip • Enter=play • ?=Help • ' + nav_text)}{_RST}")
        res = "\n".join(parts)
        _hdr_cache[cache_key] = res
        return res

    def _ep_tab_fn(opt=None, direction=1):
        nonlocal ttype, episode_ids, episode_labels, display_order, ep_opts, disabled_indices
        _hdr_cache.clear()
        target_ttype = "dub" if ttype == "sub" else "sub"
        allowed, reason = app_core.check_translation_switch_capability(show, ttype, target_ttype)
        if not allowed:
            if reason:
                app_core.set_action_feedback(show, reason)
            return (ep_opts, _ep_hdr(0), disabled_indices)

        new_ids = app_core.with_loading(
            f"Switching to {target_ttype.upper()}…",
            app_core.ensure_episode_ids,
            show,
            target_ttype,
        )
        if new_ids:
            ttype = target_ttype
            ui.ui_ttype_ctx = ttype
            episode_ids = new_ids
            ms.total_eps = len(episode_ids)
            episode_labels = _episode_labels_for(show, ttype)
            display_order = list(range(len(episode_ids)))
            if app_core.get_episode_order(ms.show_id, cfg.get("episode_order", "asc")) == "desc":
                display_order.reverse()
            ep_opts = [_build_ep_option(episode_ids[i]) for i in display_order]
            disabled_indices = _compute_disabled_indices()
        else:
            p_name = (show.get("_provider_name") or (show.get("_provider") or "").title() or "this provider") if show else "this provider"
            app_core.set_action_feedback(show, f"{target_ttype.upper()} unavailable on {p_name}")
        return (ep_opts, _ep_hdr(0), disabled_indices)

    def _ep_reverse_fn(opt=None):
        nonlocal ep_opts, display_order, disabled_indices
        _hdr_cache.clear()
        app_core.toggle_episode_order(ms.show_id, cfg.get("episode_order", "asc"))
        display_order.reverse()
        ep_opts = [_build_ep_option(episode_ids[i]) for i in display_order]
        disabled_indices = _compute_disabled_indices()
        new_order = app_core.get_episode_order(ms.show_id, cfg.get("episode_order", "asc"))
        app_core.set_action_feedback(show, f"Order: {'Newest first (N → 1)' if new_order == 'desc' else 'Oldest first (1 → N)'}")
        return (ep_opts, _ep_hdr(0), disabled_indices)

    while True:
        if ms.total_eps <= 1:
            idx = 0
        else:
            direct_single = ui.ep_prev_state == "SEARCH" and len(ms.shows) <= 1 and ms.just_searched
            hd6 = picker_help(
                "Play episode",
                "New search" if direct_single else "Go back",
                "Quit" if direct_single else "Go back",
                "Toggle Sub/Dub",
                reverse_label="Flip order",
            )
            init_sel = display_order.index(ms.current_ep_index) if ms.current_ep_index in display_order else 0
            idx = tui_pick(
                flags, ui,
                "Select episode", ep_opts,
                header_fn=_ep_hdr,
                tab_fn=_ep_tab_fn,
                reverse_fn=_ep_reverse_fn,
                info_fn=app_core.make_single_show_info_fn(ui.ui_show_ctx, ui),
                help_dict=hd6,
                disabled_indices=disabled_indices,
                initial_selected=init_sel,
            )

        if idx in (-2, -3):
            return ui.ep_prev_state or "DETAILS"

        target_idx = display_order[idx]
        target_eid = episode_id_at(episode_ids, target_idx)
        target_lbl = episode_label(target_eid, episode_labels)
        if getattr(ms, "_is_downloads", False) and not _is_ep_downloaded(target_eid, target_lbl):
            app_core.set_action_feedback(show, f"Episode {target_lbl} is not downloaded.")
            _hdr_cache.clear()
            if ms.total_eps <= 1:
                return ui.ep_prev_state or "DETAILS"
            continue

        ms.current_ep_index = target_idx
        ms.current_ep = target_eid
        ms._android_pending_watched_ep = None
        ms._android_pending_watched_idx = None
        ui.action_prev_state = "EPISODE"
        ms.selected_stream = None
        app_core._clear_streams()
        return "PLAY"
