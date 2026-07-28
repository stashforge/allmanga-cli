"""
Playback state handlers for allmanga-cli.
"""

from __future__ import annotations
from allmanga_cli import app_core
from allmanga_cli.core import streams
from allmanga_cli.ui.picker import tui_pick

import os
import re
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..context import CliFlags, UiState, MachineState

from ..domain.episodes import episode_id_at, episode_index_for_id, episode_progress_number, episode_label
from ..domain.titles import get_show_display_title
from ..domain.tracking import tracking_status_for_progress
from ..providers.shared.models import title_provider_key
from ..playback.rules import (
    playback_looks_complete,
    playback_updates_history,
    should_clear_query_on_child_left,
    marked_watched_osd,
    sync_queued_osd,
    pending_completion_osd
)
from ..ui.help import picker_help
from ..ui import picker as _picker_mod
from ..ui.verification import verification_page
from ..core.terminal import truncate_display as _truncate_display

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
_C_HINT = "\033[38;5;244m"
_RST    = "\033[0m"
GREEN   = "\033[1;32m"
YELLOW  = "\033[1;33m"
RED     = "\033[1;31m"
RESET   = "\033[0m"


def _episode_labels_for(show: dict, ttype: str) -> dict:
    if not show or show.get("_episode_labels_ttype") != ttype:
        return {}
    return show.get("_episode_labels") or {}


def _display_episode_label(show: dict, episode_id, ttype: str) -> str:
    labels = _episode_labels_for(show, ttype)
    return str(labels.get(str(episode_id)) or episode_id)

def _fmt_ep(label):
    label_str = str(label).strip()
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
    app_core._clear_streams()


def format_mirror_label(stream: dict, *, prefix: str = "", safe_tag: str = "") -> str:
    name = str(stream.get("source_name") or "Unknown")
    stream_type = str(stream.get("type") or "?").upper()
    resolution = str(stream.get("resolution") or "?")
    parts = [f"{prefix}{name}"]
    if f"[{stream_type}" not in name.upper():
        parts.append(f"[{stream_type}{safe_tag}]")
    elif safe_tag and "✓" not in name:
        parts.append(safe_tag.strip())
    if resolution != "?" and resolution.casefold() not in name.casefold():
        parts.append(resolution)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _handle_verification_page(
    flags: "CliFlags",
    ui: "UiState",
    ms: "MachineState",
    cfg: dict,
    ttype: str,
) -> str:
    show = ui.ui_show_ctx or {}
    episode_url = show.get("_provider_verification_url", "")
    fallback_url = app_core.allanime_frontend_domain(cfg)
    status_msg = ""

    while True:
        result = verification_page(
            get_show_display_title(show) if show else ms.show_title,
            ms.current_ep,
            ttype,
            episode_url,
            fallback_url,
            legacy_url="https://allmanga.to",
            status_message=status_msg,
        )
        if result == "back":
            return "ACTION_MENU"
        if result == "open_episode":
            if episode_url and app_core.open_external_url(episode_url):
                status_msg = "Opened episode page. Verify, then choose retry."
            elif episode_url:
                status_msg = "Could not open browser. Copy the episode URL manually."
            else:
                status_msg = "Episode URL is unavailable."
        elif result == "open_site":
            if app_core.open_external_url(fallback_url):
                status_msg = "Opened provider site. Verify, then choose retry."
            else:
                status_msg = "Could not open browser. Copy the site URL manually."
        elif result == "retry":
            _clear_episode_source_state(ms)
            ep_label = _display_episode_label(show, ms.current_ep, ttype)
            app_core.set_action_feedback(show, f"Retrying EP {ep_label} after verification.")
            return "PLAY"


def _open_provider_verification(
    flags: "CliFlags",
    ui: "UiState",
    ms: "MachineState",
    cfg: dict,
    ttype: str,
    feedback: str,
) -> str:
    app_core._exit_player_screen()
    _clear_episode_source_state(ms)
    verification_url = app_core.allanime_episode_url(
        ms.show_id,
        ms.current_ep,
        ttype,
        cfg,
    )
    ui.ui_show_ctx["_provider_verification_url"] = verification_url
    ui.ui_show_ctx["_provider_verification_episode"] = str(ms.current_ep)
    app_core.set_action_feedback(ui.ui_show_ctx, feedback)
    return "PROVIDER_VERIFY"


def handle_provider_verify_state(
    flags: "CliFlags",
    ui: "UiState",
    ms: "MachineState",
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,
) -> str:
    del args, resolve_tracking_fn
    return _handle_verification_page(flags, ui, ms, cfg, ttype)


def handle_episode_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    show = ui.ui_show_ctx
    episode_ids = app_core.ensure_episode_ids(show, ttype)
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

    ep_opts = [episode_label(episode_ids[i], episode_labels) for i in display_order]

    def _ep_hdr(si):
        try: w = os.get_terminal_size().columns
        except OSError: w = 80
        parts = []
        if show:
            app_core.build_info_panel(show, ttype, w, parts, local_only=getattr(ms, "_is_downloads", False))

        _t = lambda s: _truncate_display(s, max(1, w - 1))
        direct_single = ui.ep_prev_state == "SEARCH" and len(ms.shows) <= 1 and ms.just_searched
        nav_text = "Left=search  Esc=quit" if direct_single else "Left/Esc=back"
        feedback_time = float((show or {}).get("_action_feedback_time") or 0)
        feedback_msg = (show or {}).get("_action_feedback") or ""

        if feedback_msg and time.time() - feedback_time < 2.0:
            parts.append(f"\033[38;5;220m{_t(feedback_msg)}{_RST}")
        else:
            parts.append(f"{_C_HINT}{_t(f'Enter/Right=select  Ctrl+R=flip  ? = Help  {nav_text}')}{_RST}")
        return "\n".join(parts)

    def _ep_tab_fn(opt=None):
        nonlocal ep_opts, display_order
        app_core.toggle_episode_order(ms.show_id, cfg.get("episode_order", "asc"))
        display_order.reverse()
        ep_opts = [episode_label(episode_ids[i], episode_labels) for i in display_order]
        return (ep_opts, _ep_hdr(0))

    if ms.total_eps <= 1:
        idx = 0
    else:
        direct_single = ui.ep_prev_state == "SEARCH" and len(ms.shows) <= 1 and ms.just_searched
        hd6 = picker_help(
            "Play episode",
            "New search" if direct_single else "Go back",
            "Quit" if direct_single else "Go back",
            "Flip order",
            reverse_label="Flip order",
        )
        idx = tui_pick(
            flags, ui,
            "Select episode", ep_opts,
            header_fn=_ep_hdr,
            tab_fn=_ep_tab_fn,
            reverse_fn=_ep_tab_fn,
            info_fn=app_core.make_single_show_info_fn(ui.ui_show_ctx, ui),
            help_dict=hd6
        )

    if idx == -2:
        previous = ui.ep_prev_state
        if previous == "SEARCH" and len(ms.shows) <= 1 and ms.just_searched:
            return "QUIT"
        else:
            return previous

    elif idx == -3:
        previous = ui.ep_prev_state
        direct_single = ui.ep_prev_state == "SEARCH" and len(ms.shows) <= 1 and ms.just_searched
        if should_clear_query_on_child_left(previous, direct_single):
            ms.query_str = ""
        return previous

    else:
        ms.current_ep_index = display_order[idx]
        ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
        ui.action_prev_state = "EPISODE"
        ms.selected_stream = None
        app_core._clear_streams()
        return "PLAY"


def handle_play_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    quality: str,
    resolve_tracking_fn,
) -> str:
    app_core.enter_alt_screen()

    s_ctx = ui.ui_show_ctx
    sync_enabled = resolve_tracking_fn(ui.search_prev_state, args, cfg, s_ctx)
    app_core.prepare_show_display_state(s_ctx, ttype, sync_enabled)
    ms.show_title = get_show_display_title(s_ctx, sync_enabled=sync_enabled)
    ms.show_id = s_ctx.get("_id")
    al_id = app_core.get_show_anilist_id(s_ctx)
    episode_ids = app_core.ensure_episode_ids(s_ctx, ttype)

    if not episode_ids:
        app_core._exit_player_screen()
        app_core.err(app_core.episode_catalog_error(s_ctx))
        return "DETAILS"

    ms.total_eps = len(episode_ids) or ms.total_eps
    ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep)

    if ms.current_ep_index is None:
        app_core._exit_player_screen()
        app_core.err(f"EP {ms.current_ep} is not present in the provider catalog.")
        return "EPISODE"

    ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
    episode_labels = _episode_labels_for(s_ctx, ttype)
    current_ep_label = _display_episode_label(s_ctx, ms.current_ep, ttype)

    _player_ui_state = app_core._player_ui_state
    _player_ui_state.update({
        "active": True,
        "show": ui.ui_show_ctx,
        "current_ep": ms.current_ep,
        "current_ep_label": current_ep_label,
        "total_eps": ms.total_eps,
        "status_lines": [],
        "stream_info": {},
        "mpv_props": None,
        "_cleared_terminal_image": False,
        "_last_poster_key": None,
    })

    # Try to trigger the render function from ui module directly if we can't use globals
    try:
        from ..ui.player_screen import render as _render_player_screen
        _render_player_screen(
            poster_manager=getattr(app_core, "_poster_manager", None),
            ui=ui,
        )
    except ImportError:
        pass


    provider_id = title_provider_key(ui.ui_show_ctx)
    _cache_key = (ms.show_id, ms.current_ep, ttype, provider_id)
    if _cache_key == ms.ep_cache_key and ms.ep_cache_data:
        ep_data = ms.ep_cache_data
    else:
        app_core.info(f"Loading {_fmt_ep(current_ep_label)} metadata...")
        ep_data = app_core.get_episode_data(
            ms.show_id,
            ms.current_ep,
            ttype,
            provider_id=provider_id,
        )
        ms.ep_cache_key  = _cache_key
        ms.ep_cache_data = ep_data

    if not ep_data:
        app_core._exit_player_screen()
        _clear_episode_source_state(ms)
        app_core.set_action_feedback(
            ui.ui_show_ctx,
            f"Could not load {_fmt_ep(current_ep_label)}. Check connection or try another mirror.",
        )
        return "ACTION_MENU"
    if ep_data.get("_provider_error") == "browser_verification_required":
        return _open_provider_verification(
            flags,
            ui,
            ms,
            cfg,
            ttype,
            "Browser verification required. Open the site in a browser, play once, then replay.",
        )
    ui.ui_show_ctx.pop("_provider_verification_url", None)
    ui.ui_show_ctx.pop("_provider_verification_episode", None)
    ui.ui_show_ctx.pop("_provider_verification_seen", None)

    first_source_name = None
    if ms.selected_stream is None:
        app_core._clear_streams()

        _ipc_player = app_core._ipc_player
        if getattr(ms, "_is_downloads", False):
            filepath = ms._download_files.get(str(ms.current_ep))
            if filepath:
                res = (filepath, "Local File", filepath, [])
            else:
                res = None
        elif _ipc_player.prefetched_ep == ms.current_ep and _ipc_player.prefetched_res:
            res = _ipc_player.prefetched_res
            _ipc_player.prefetched_ep = None
            _ipc_player.prefetched_stream = None
            _ipc_player.prefetched_res = None
        else:
            app_core.info("Finding a playable stream...")
            res = app_core.fetch_episode_stream(
                ms.show_id,
                ms.current_ep,
                ttype,
                cfg.get("quality", "best"),
                provider_id=provider_id,
            )

        if res:
            ms.selected_stream, first_source_name, _, streams = res
            app_core._extend_streams(streams)

    if args.sources and not ui.initial_sources_prompted:
        ui.initial_sources_prompted = True
        if first_source_name is not None:
            app_core.start_bg_resolve(ep_data, {first_source_name})
        app_core._exit_player_screen()
        return "MIRRORS"

    if ms.selected_stream is None:
        app_core._exit_player_screen()
        _clear_episode_source_state(ms)
        app_core.set_action_feedback(
            ui.ui_show_ctx,
            "No playable streams found. Try another mirror.",
        )
        return "ACTION_MENU"

    if args.print_url:
        app_core._exit_player_screen(close_alt=True)
        print(ms.selected_stream["link"])
        audio_url = ms.selected_stream.get("audio_url", "")
        if audio_url:
            print(f"Audio: {audio_url}")
        ref = ms.selected_stream.get("referer","")
        if ref: print(f"Referer: {ref}")
        return "QUIT"

    if getattr(args, 'download', False):
        app_core._exit_player_screen(close_alt=True)
        
        exclude_sources = set()
        download_ok = False
        downloader_choice = getattr(args, "downloader", cfg.get("downloader", "auto"))
        
        extra_args = getattr(args, "extra_args", [])
        if extra_args and extra_args[0] == "--":
            extra_args = extra_args[1:]
        
        while True:
            download_ok = app_core.download_episode(
                ms.show_title, ms.current_ep, ms.selected_stream, 
                cfg.get("download_dir", ""), downloader=downloader_choice,
                extra_args=extra_args
            )
            if download_ok:
                try:
                    from allmanga_cli.core.storage import load_downloads_db, save_downloads_db
                    db = load_downloads_db()
                    title = ms.show_title
                    if title not in db["shows"]:
                        db["shows"][title] = {"episodes": []}
                    db["shows"][title]["metadata"] = s_ctx
                    ep_str = str(ms.current_ep)
                    if ep_str not in db["shows"][title]["episodes"]:
                        db["shows"][title]["episodes"].append(ep_str)
                    save_downloads_db(db)
                except Exception as e:
                    pass
                break
            
            exclude_sources.add(first_source_name)
            print(f"{YELLOW}Download failed on mirror '{first_source_name}'. Trying next mirror...{RESET}")
            
            res = app_core.fetch_episode_stream(
                ms.show_id,
                ms.current_ep,
                ttype,
                cfg.get("quality", "best"),
                provider_id=provider_id,
                exclude_sources=exclude_sources
            )
            if not res:
                break
            ms.selected_stream, first_source_name, _, streams = res
            app_core._extend_streams(streams)

        if not download_ok:
            print(f"\n{RED}All mirrors failed for EP {ms.current_ep}. Skipping to next episode...{RESET}")

        download_batch_end = ms.download_batch_end if ms.download_batch_end is not None else ms.current_ep
        if int(float(str(download_batch_end))) > int(float(str(ms.current_ep))) and ms.current_ep_index + 1 < ms.total_eps:
            ms.current_ep_index += 1
            ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            ms.selected_stream = None
            app_core._clear_streams()
            return "PLAY"
        else:
            print(f"\n{GREEN}Downloads complete.{RESET}")
            return "QUIT"

    # ── Launch player ─────────────────────────────────────────────
    def fetch_cb(ep_num):
        if isinstance(ep_num, int) and 1 <= ep_num <= len(episode_ids):
            ep_idx = ep_num - 1
        else:
            ep_idx = episode_index_for_id(episode_ids, ep_num)
        if ep_idx is None:
            return None
        return app_core.fetch_episode_stream(
            ms.show_id,
            episode_id_at(episode_ids, ep_idx),
            ttype,
            cfg.get("quality", "best"),
            provider_id=provider_id,
        )

    is_binge = args.binge or cfg.get("binge", False)

    if app_core.is_termux():
        player = args.player or cfg.get("player","mpv")
        if player=="mpv" and not args.player:
            if (not app_core.pkg_installed("is.xyz.mpv")
                    and app_core.pkg_installed("app.marlboroadvance.mpvex")):
                player = "mpvex"

        result = app_core.play_android(
            ms.show_title,
            current_ep_label,
            ms.selected_stream,
            fetch_cb,
            player,
            ms.total_eps,
            ms.show_id,
            is_binge,
        )

        if first_source_name is not None:
            exclude = {first_source_name}
            app_core.start_bg_resolve(ep_data, exclude)

        if result == "NEXT" and ms.current_ep_index + 1 < ms.total_eps:
            ms.current_ep_index += 1
            ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            ms.selected_stream = None
            app_core._clear_streams()
            return "PLAY"

        elif result == "PREV" and ms.current_ep_index > 0:
            ms.current_ep_index -= 1
            ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            ms.selected_stream = None
            app_core._clear_streams()
            return "PLAY"

        verification_url = ui.ui_show_ctx.get("_provider_verification_url", "")
        verification_episode = ui.ui_show_ctx.get("_provider_verification_episode")
        if verification_url and str(verification_episode) == str(ms.current_ep):
            app_core._exit_player_screen()
            return "PROVIDER_VERIFY"

        app_core._exit_player_screen()
        return "ACTION_MENU"

    else:
        if first_source_name is not None:
            exclude = {first_source_name}
            app_core.start_bg_resolve(ep_data, exclude)

        next_episode = episode_id_at(episode_ids, ms.current_ep_index + 1) if ms.current_ep_index + 1 < ms.total_eps else None

        result, percent, time_pos, duration, played_seconds = app_core.play_desktop(
            ms.show_title, current_ep_label, ms.selected_stream, fetch_cb,
            ms.total_eps, is_binge, ms.show_id, ms.pending_osd_msg,
            ms.current_ep_index, next_episode
        )

        ms.pending_osd_msg = ""
        app_core._exit_player_screen()

        # Smart Auto-Scrobble & Timestamping (80% OR <150s remaining)
        auto_scrobbled = playback_looks_complete(
            result, percent, time_pos, duration, played_seconds
        )
        pending_completion = app_core.get_pending_completion(ms.show_id)

        if (pending_completion
                and str(pending_completion.get("next_episode")) == str(ms.current_ep)
                and str(pending_completion.get("episode")) != str(ms.current_ep)
                and time_pos >= 120):
            pending_ep = pending_completion.get("episode")
            pending_progress = int(pending_completion.get("progress") or 0)
            sync_pending = resolve_tracking_fn(ui.search_prev_state, args, cfg)

            if sync_pending:
                tkn = cfg.get("anilist_token")
                if tkn and pending_progress:
                    show_ctx = ui.ui_show_ctx
                    new_status = tracking_status_for_progress(show_ctx, pending_progress)

                    def _pending_sync_success(ep=pending_ep, ctx=show_ctx):
                        app_core.set_action_feedback(ctx, f"AniList synced: EP {ep} watched.")
                    def _pending_sync_failure(ctx=show_ctx):
                        app_core.set_action_feedback(ctx, "Saved locally, but AniList sync is pending.")

                    queued = app_core.queue_anilist_progress(
                        tkn, ms.show_title, pending_progress, al_id,
                        show_ctx, ttype, new_status,
                        on_success=_pending_sync_success,
                        on_failure=_pending_sync_failure,
                        pending_completion={
                            "show_id": str(ms.show_id),
                            "episode": str(pending_ep),
                        },
                    )
                    if queued:
                        app_core.set_action_feedback(show_ctx, f"AniList sync queued: EP {pending_ep}.")
                else:
                    sync_pending = False

            if not sync_pending:
                app_core.save_resume_time(ms.show_id, pending_ep, 0)
                app_core.clear_pending_completion(ms.show_id)

        should_update_history = (
            not sync_enabled
            and playback_updates_history(
            result, percent, time_pos, duration, played_seconds
            )
        )
        if should_update_history:
            app_core.save_history(ui.ui_show_ctx, ms.current_ep, ttype)

        if auto_scrobbled:
            app_core.save_resume_time(ms.show_id, ms.current_ep, 0)
        elif time_pos > 30:
            app_core.save_resume_time(ms.show_id, ms.current_ep, time_pos)

        if result == "QUIT" or result == "EOF":
            if auto_scrobbled and resolve_tracking_fn(ui.search_prev_state, args, cfg):
                tkn = cfg.get("anilist_token")
                if tkn:
                    show_ctx = ui.ui_show_ctx
                    progress_ep = episode_progress_number(ms.current_ep, ms.current_ep_index + 1)
                    new_status = tracking_status_for_progress(show_ctx, progress_ep)
                    queued = app_core.queue_anilist_progress(
                        tkn, ms.show_title, progress_ep, al_id,
                        show_ctx, ttype, new_status,
                        on_success=lambda ep=ms.current_ep, ctx=show_ctx:
                            app_core.set_action_feedback(ctx, f"AniList synced: EP {ep} watched."),
                        on_failure=lambda ctx=show_ctx:
                            app_core.set_action_feedback(ctx, "Saved locally, but AniList sync is pending."),
                    )
                    if queued:
                        app_core.set_action_feedback(show_ctx, f"AniList sync queued: EP {ms.current_ep}.")

            if result == "EOF" and (args.binge or cfg.get("binge")):
                if ms.current_ep_index + 1 < ms.total_eps:
                    next_ep = episode_id_at(episode_ids, ms.current_ep_index + 1)
                    if flags.incognito_mode:
                        ms.pending_osd_msg = None
                    elif auto_scrobbled:
                        ms.pending_osd_msg = marked_watched_osd(
                            ms.current_ep,
                            resolve_tracking_fn(ui.search_prev_state, args, cfg)
                        )
                    else:
                        progress_ep = episode_progress_number(ms.current_ep, ms.current_ep_index + 1)
                        app_core.save_pending_completion(
                            ms.show_id, ms.current_ep, progress_ep,
                            next_ep, time_pos, duration
                        )
                        if time_pos > 0:
                            app_core.save_resume_time(ms.show_id, ms.current_ep, time_pos)
                        ms.pending_osd_msg = pending_completion_osd(ms.current_ep, next_ep)

                    ms.current_ep_index += 1
                    ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
                    ms.selected_stream = None
                    app_core._clear_streams()
                    return "PLAY"
                else:
                    app_core._ipc_player.quit()
                    print(f"\n{GREEN}Finished the last episode.{RESET}")
                    return "QUIT"
            else:
                app_core._ipc_player.quit()
                return "ACTION_MENU"

        elif result == "NEXT":
            if ms.current_ep_index + 1 < ms.total_eps:
                next_ep = episode_id_at(episode_ids, ms.current_ep_index + 1)
                if flags.incognito_mode:
                    ms.pending_osd_msg = None
                elif auto_scrobbled and resolve_tracking_fn(ui.search_prev_state, args, cfg):
                    tkn = cfg.get("anilist_token")
                    if tkn:
                        show_ctx = ui.ui_show_ctx
                        progress_ep = episode_progress_number(ms.current_ep, ms.current_ep_index + 1)
                        new_status = tracking_status_for_progress(show_ctx, progress_ep)
                        queued = app_core.queue_anilist_progress(
                            tkn, ms.show_title, progress_ep, al_id,
                            show_ctx, ttype, new_status,
                            on_success=lambda ep=ms.current_ep, ctx=show_ctx:
                                app_core.set_action_feedback(ctx, f"AniList synced: EP {ep} watched."),
                            on_failure=lambda ctx=show_ctx:
                                app_core.set_action_feedback(ctx, "Saved locally, but AniList sync is pending."),
                        )
                        ms.pending_osd_msg = (
                            sync_queued_osd(ms.current_ep)
                            if queued else marked_watched_osd(ms.current_ep, False)
                        )
                elif not auto_scrobbled:
                    progress_ep = episode_progress_number(ms.current_ep, ms.current_ep_index + 1)
                    app_core.save_pending_completion(ms.show_id, ms.current_ep, progress_ep, next_ep, time_pos, duration)
                    if time_pos > 0:
                        app_core.save_resume_time(ms.show_id, ms.current_ep, time_pos)
                    ms.pending_osd_msg = pending_completion_osd(ms.current_ep, next_ep)

                ms.current_ep_index += 1
                ms.current_ep = next_ep
                ms.selected_stream = None
                app_core._clear_streams()
                return "PLAY"
            else:
                app_core._ipc_player.quit()
                print(f"\n{GREEN}Finished the last episode.{RESET}")
                return "QUIT"

        elif result == "PREV":
            if ms.current_ep_index > 0:
                ms.current_ep_index -= 1
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
                ms.selected_stream = None
                app_core._clear_streams()
                return "PLAY"
            else:
                app_core._ipc_player.quit()
                return "ACTION_MENU"
        else:
            app_core._ipc_player.quit()
            return "ACTION_MENU"


def handle_action_menu_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:
    opts, acts = [], []
    is_tracking = resolve_tracking_fn(ui.search_prev_state, args, cfg)
    action_show = ui.ui_show_ctx
    episode_ids = app_core.ensure_episode_ids(action_show, ttype)

    if not episode_ids:
        app_core.err(app_core.episode_catalog_error(action_show))
        return "DETAILS"

    ms.total_eps = len(episode_ids) or ms.total_eps
    ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep)

    if ms.current_ep_index is None:
        app_core.err(f"EP {ms.current_ep} is not present in the provider catalog.")
        return "EPISODE"

    next_ep = episode_id_at(episode_ids, ms.current_ep_index + 1) if ms.current_ep_index + 1 < ms.total_eps else None
    prev_ep = episode_id_at(episode_ids, ms.current_ep_index - 1) if ms.current_ep_index > 0 else None
    episode_labels = _episode_labels_for(action_show, ttype)
    current_ep_label = _display_episode_label(action_show, ms.current_ep, ttype)
    next_ep_label = episode_labels.get(str(next_ep), str(next_ep)) if next_ep is not None else ""
    prev_ep_label = episode_labels.get(str(prev_ep), str(prev_ep)) if prev_ep is not None else ""

    if not flags.incognito_mode:
        if next_ep is not None:
            opts.append("Mark & Next"); acts.append("TRACK_NEXT")
        opts.append("Mark Watched"); acts.append("TRACK_ONLY")

    if next_ep is not None: opts.append("Next");    acts.append("NEXT")
    if prev_ep is not None: opts.append("Previous"); acts.append("PREV")
    if ms.total_eps > 1: opts.append("Episodes"); acts.append("EPISODES")

    verification_url = action_show.get("_provider_verification_url", "")
    verification_episode = action_show.get("_provider_verification_episode")
    if verification_url and str(verification_episode) == str(ms.current_ep):
        opts.append("Verify")
        acts.append("VERIFY")

    opts += ["Replay"]
    acts += ["REPLAY"]
    if not getattr(ms, "_is_downloads", False):
        opts += ["Browser", "Mirror"]
        acts += ["BROWSER_PLAY", "MIRRORS"]
    opts += ["Back", "Quit"]
    acts += ["BACK", "QUIT"]

    action_hints = {}
    from allmanga_cli.domain.episodes import anilist_progress_target_for_episode
    target_prog = anilist_progress_target_for_episode(ms.current_ep, fallback=None)
    try:
        current_al = max(0, int(action_show.get("_anilist_progress") or 0))
    except (TypeError, ValueError):
        current_al = 0

    if is_tracking and target_prog is not None:
        if current_al and int(current_al) >= target_prog:
            sync_txt = f"save {_fmt_ep(current_ep_label)} · AL already EP {current_al}"
        else:
            sync_txt = f"save {_fmt_ep(current_ep_label)} · sync AL EP {target_prog}"
    elif is_tracking:
        sync_txt = f"save {_fmt_ep(current_ep_label)} · sync AL EP {current_ep_label}"
    else:
        sync_txt = f"save {_fmt_ep(current_ep_label)}"

    for opt, act in zip(opts, acts):
        if act == "TRACK_ONLY": action_hints[opt] = sync_txt
        elif act == "TRACK_NEXT": action_hints[opt] = f"{sync_txt} · play EP {next_ep_label}"
        elif act == "NEXT":     action_hints[opt] = f"EP {next_ep_label}"
        elif act == "PREV":   action_hints[opt] = f"EP {prev_ep_label}"
        elif act == "EPISODES": action_hints[opt] = "browse all"
        elif act == "VERIFY": action_hints[opt] = "verification"
        elif act == "REPLAY": action_hints[opt] = f"{_fmt_ep(current_ep_label)} again"
        elif act == "BROWSER_PLAY": action_hints[opt] = "open url in browser"
        elif act == "MIRRORS":action_hints[opt] = "switch source"
        elif act == "BACK":   action_hints[opt] = "Back"
        elif act == "QUIT":   action_hints[opt] = "Quit"

    def _action_hdr(si):
        C_T  = "\033[1;97m"
        C_D  = "\033[38;5;248m"
        C_K  = "\033[38;5;244m"
        R    = "\033[0m"
        try: w = os.get_terminal_size().columns
        except OSError: w = 80

        n = app_core._stream_count()
        _bg_lock = streams._bg_lock
        _bg_thread = streams._bg_thread
        _bg_stats = streams._bg_stats

        with _bg_lock:
            bg_alive = _bg_thread and _bg_thread.is_alive()
            r, f = _bg_stats["resolved"], _bg_stats["failed"]
            tot = _bg_stats.get('total', r+f)

        if bg_alive and (r + f) < tot:
            from allmanga_cli.ui.spinner import spinner_frame, spinner_from_config
            spinner = spinner_frame(spinner_from_config(cfg))
            mstat = f"{C_D}{spinner} {n} streams found • checking sources ({r+f}/{tot}){R}"
        elif n > 0:
            mstat = f"{C_D}✔ {n} streams ready • {tot}/{tot} sources checked{R}"
        else:
            mstat = ""

        parts = []
        feedback_time = action_show.get("_action_feedback_time", 0)
        has_feedback = (time.time() - float(feedback_time)) < 3.0 if feedback_time else False
        feedback_msg = action_show.get("_action_feedback", "")

        ep_str = current_ep_label
        app_core.build_info_panel(action_show, ttype, w, parts, override_ep_str=ep_str, local_only=getattr(ms, "_is_downloads", False))

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
    idx = tui_pick(
        flags, ui,
        "Select action", opts,
        header_fn=_action_hdr,
        info_fn=app_core.make_single_show_info_fn(action_show, ui),
        hints=action_hints,
        help_dict=hd7
    )

    if idx in (-2, -3):
        if ms.total_eps <= 1:
            return ui.ep_prev_state
        return ui.action_prev_state

    def _execute_track_action():
        tkn = cfg.get("anilist_token")
        synced = False
        if tkn and resolve_tracking_fn(ui.search_prev_state, args, cfg, action_show):
            progress_ep = episode_progress_number(ms.current_ep, ms.current_ep_index + 1)
            al_id = app_core.get_show_anilist_id(action_show)
            result = app_core.with_loading(
                f"Syncing AniList progress: EP {progress_ep}…",
                app_core.sync_watched_to_anilist,
                tkn, ms.show_title, progress_ep, al_id, action_show, ttype,
            )
            if result:
                synced = True
                app_core.set_action_feedback(action_show, f"AniList synced: EP {progress_ep} watched.")
            else:
                app_core.set_action_feedback(action_show, "AniList sync failed.")
        else:
            app_core.with_loading(
                f"Saving {_fmt_ep(current_ep_label)} locally…",
                app_core.save_history, action_show, ms.current_ep, ttype
            )
            app_core.set_action_feedback(action_show, f"Marked {_fmt_ep(current_ep_label)} as watched locally.")

        app_core.save_resume_time(ms.show_id, ms.current_ep, 0)
        return synced

    a = acts[idx]
    if a == "TRACK_ONLY":
        _execute_track_action()
        return "ACTION_MENU"

    elif a == "TRACK_NEXT":
        synced = _execute_track_action()
        ms.pending_osd_msg = marked_watched_osd(ms.current_ep, synced)
        ms.current_ep_index += 1
        ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
        _clear_episode_source_state(ms)
        return "PLAY"

    elif a == "NEXT":
        ms.current_ep_index += 1
        ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
        _clear_episode_source_state(ms)
        return "PLAY"

    elif a == "PREV":
        ms.current_ep_index -= 1
        ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
        _clear_episode_source_state(ms)
        return "PLAY"

    elif a == "EPISODES":
        ui.ep_prev_state = "ACTION_MENU"
        return "EPISODE"

    elif a == "VERIFY":
        return "PROVIDER_VERIFY"

    elif a == "REPLAY":
        _clear_episode_source_state(ms)
        return "PLAY"

    elif a == "MIRRORS":
        return "MIRRORS"

    elif a == "BROWSER_PLAY":
        return "BROWSER_PLAY"

    elif a == "BACK":
        if ms.total_eps <= 1:
            return ui.ep_prev_state
        return ui.action_prev_state

    elif a == "QUIT":
        return "QUIT"

    return "ACTION_MENU"


def handle_mirrors_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:

    def _mlabel(s):
        tag = " ✓" if s.get("android_safe") else ""
        pref = app_core.get_preferred_mirror(ms.show_id)
        is_pref = pref.get("source_name") == s["source_name"] and pref.get("resolution") == s.get("resolution", "?")

        if ms.selected_stream and s.get("link") == ms.selected_stream.get("link"):
            prefix = "▶ "
        elif is_pref:
            prefix = "★ "
        else:
            prefix = ""

        return format_mirror_label(s, prefix=prefix, safe_tag=tag)

    def _dedup():
        seen, out = set(), []
        for s in sorted(app_core._stream_snapshot(), key=lambda x: x.get("source_priority",4)):
            if s["link"] not in seen:
                seen.add(s["link"])
                out.append(s)
        return out

    _live_deduped = []

    def _mirror_refresh(q=""):
        nonlocal _live_deduped
        _live_deduped = _dedup()
        mopts = [_mlabel(s) for s in _live_deduped]

        _bg_lock = streams._bg_lock
        _bg_thread = streams._bg_thread
        _bg_stats = streams._bg_stats

        with _bg_lock:
            alive = _bg_thread and _bg_thread.is_alive()
            r, f = _bg_stats["resolved"], _bg_stats["failed"]
            tot = _bg_stats.get('total', r+f)

        C_T  = "\033[1;97m"
        C_D  = "\033[38;5;248m"
        C_K  = "\033[38;5;244m"
        R    = "\033[0m"

        try: w = os.get_terminal_size().columns
        except OSError: w = 80

        if alive and (r + f) < tot:
            from allmanga_cli.ui.spinner import spinner_frame, spinner_from_config
            spinner = spinner_frame(spinner_from_config(cfg))
            plain_status = f"{spinner} {len(mopts)} streams found • checking sources ({r+f}/{tot})"
        else:
            plain_status = f"✔ {len(mopts)} streams ready • {tot}/{tot} sources checked"

        parts = []
        if ui.ui_show_ctx:
            ep_str = _display_episode_label(ui.ui_show_ctx, ms.current_ep, ttype)
            app_core.build_info_panel(ui.ui_show_ctx, ttype, w, parts, override_ep_str=ep_str, local_only=getattr(ms, "_is_downloads", False))

        toast = ui.pref_toast
        toast_time = ui.pref_toast_time
        footer = lambda s: _truncate_display(s, max(1, w - 1))

        if toast and time.time() - toast_time < 3:
            parts.append(f"\033[38;5;220m* {footer(toast)}\033[0m")
        else:
            parts.append(f"{C_D}{footer(f'{plain_status}  │  ? = Help  Esc=back')}{R}")

        hdr = "\n".join(parts)
        return mopts, hdr, not alive

    init_opts, init_hdr, _ = _mirror_refresh()
    if not init_opts:
        with streams._bg_lock:
            still_alive = streams._bg_thread and streams._bg_thread.is_alive()
        if not still_alive:
            if ui.ui_show_ctx:
                app_core.set_action_feedback(
                    ui.ui_show_ctx,
                    "No mirrors available. Try replay after browser verification.",
                )
            return "ACTION_MENU"

    def _tab_pref(opt_idx):
        if 0 <= opt_idx < len(_live_deduped):
            s = _live_deduped[opt_idx]
            app_core.toggle_preferred_mirror(ms.show_id, s["source_name"], s.get("resolution", "?"))
            ui.pref_toast = "Preferred server updated (Will apply on next playback)"
            ui.pref_toast_time = time.time()
        return _mirror_refresh()[:2]

    hd8 = picker_help("Play stream", "Go back", "Go back", "Mark preferred")
    ui.pref_toast = ""

    midx = tui_pick(
        flags, ui,
        "Select mirror", init_opts,
        header=init_hdr,
        live_fn=_mirror_refresh,
        tab_fn=_tab_pref,
        info_fn=app_core.make_single_show_info_fn(ui.ui_show_ctx, ui),
        help_dict=hd8
    )

    if midx in (-2, -3):
        return "ACTION_MENU"
    elif midx >= 0 and midx < len(_live_deduped):
        ms.selected_stream = _live_deduped[midx]
        return "PLAY"
    else:
        return "ACTION_MENU"

def handle_browser_play_state(
    flags: CliFlags,
    ui: UiState,
    ms: MachineState,
    cfg: dict,
    args: Any,
    ttype: str,
    resolve_tracking_fn,) -> str:

    ep_data = app_core.with_loading(
        f"Fetching {ttype.upper()} URLs...",
        app_core.get_episode_data, ms.show_id, ms.current_ep, ttype, provider_id=getattr(args, "provider", None)
    )

    if not ep_data:
        app_core.set_action_feedback(ui.ui_show_ctx, "No links found for this episode.")
        return "ACTION_MENU"

    sources = ep_data.get("episode", {}).get("sourceUrls", [])
    opts = []
    urls = []
    for s in sources:
        url = s.get("sourceUrl") or s.get("link")
        if url:
            name = s.get("sourceName", "Unknown")
            opts.append(f"{name} ({url})")
            urls.append(url)

    if not opts:
        app_core.set_action_feedback(ui.ui_show_ctx, "No valid URLs found.")
        return "ACTION_MENU"

    def _browser_hdr(si):
        try: w = os.get_terminal_size().columns
        except OSError: w = 80
        parts = []
        ep_str = _display_episode_label(ui.ui_show_ctx, ms.current_ep, ttype)
        app_core.build_info_panel(ui.ui_show_ctx, ttype, w, parts, override_ep_str=ep_str, local_only=getattr(ms, "_is_downloads", False))
        _t = lambda s: _truncate_display(s, max(1, w - 1))
        parts.append(f"\033[38;5;244m{_t('Enter/Right=select  ? = Help  Left/Esc=back')}\033[0m")
        return "\n".join(parts)

    idx = tui_pick(
        flags, ui, "Select link to open in browser", opts, header_fn=_browser_hdr,
        info_fn=app_core.make_single_show_info_fn(ui.ui_show_ctx, ui)
    )
    
    if idx < 0:
        return "ACTION_MENU"

    url = urls[idx]

    if app_core.is_termux():
        import subprocess
        try:
            subprocess.run(["termux-open-url", url], check=False)
            app_core.set_action_feedback(ui.ui_show_ctx, f"Opened {url} in Android browser")
        except Exception:
            app_core.set_action_feedback(ui.ui_show_ctx, "Failed to open link via termux-open-url")
    else:
        import webbrowser
        try:
            webbrowser.open(url)
            app_core.set_action_feedback(ui.ui_show_ctx, f"Opened {url} in browser")
        except Exception:
            app_core.set_action_feedback(ui.ui_show_ctx, "Failed to open link in browser")

    return "ACTION_MENU"
