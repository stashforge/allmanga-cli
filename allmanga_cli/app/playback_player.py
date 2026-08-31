"""Playback handler coordinating stream resolution, player runtime, and sync."""

from __future__ import annotations

import os
import sys
import time
from typing import Any


from ..context import CliFlags, UiState, MachineState
from ..domain.titles import get_show_display_title
from ..domain.episodes import (
    episode_id_at,
    episode_index_for_id,
    episode_progress_number,
)
from ..domain.tracking import tracking_status_for_progress
from ..playback.rules import (
    playback_looks_complete,
    playback_updates_history,
    marked_watched_osd,
    pending_completion_osd,
    sync_queued_osd,
)
from ..providers import title_provider_key
from ..ui.display import suppress_terminal_echo
from . import playback as playback_mod
from .. import app_core

GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
RESET = "\033[0m"



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
    ms.current_ep_index = episode_index_for_id(
        episode_ids, ms.current_ep, labels=ui.ui_show_ctx.get("_episode_labels")
    )

    if ms.current_ep_index is None:
        app_core._exit_player_screen()
        app_core.err(f"EP {ms.current_ep} is not present in the provider catalog.")
        return "EPISODE"

    ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
    current_ep_label = playback_mod._display_episode_label(s_ctx, ms.current_ep, ttype)

    is_download_mode = bool(getattr(args, 'download', False))

    if not is_download_mode:
        from ..ui.player_screen import _player_ui_state
        _player_ui_state.update({
            "active": True,
            "show": ui.ui_show_ctx,
            "ttype": ttype,
            "current_ep": ms.current_ep,
            "current_ep_label": current_ep_label,
            "total_eps": ms.total_eps,
            "status_lines": [],
            "stream_info": {},
            "mpv_props": None,
            "_cleared_terminal_image": False,
            "_last_poster_key": None,
        })

    with suppress_terminal_echo():
        provider_id = title_provider_key(ui.ui_show_ctx)
        p_name = (ui.ui_show_ctx.get("_provider_name") or ui.ui_show_ctx.get("provider_name") or provider_id).title()
        if not is_download_mode:
            _player_ui_state["loading_provider_name"] = p_name
            _player_ui_state["loading_start_time"] = time.time()

            try:
                from ..ui.player_screen import start_loading_ticker
                start_loading_ticker(
                    poster_manager=getattr(app_core, "_poster_manager", None),
                    ui=ui,
                )
            except ImportError:
                pass

        _cache_key = (ms.show_id, ms.current_ep, ttype, provider_id)
        if getattr(ms, "_is_downloads", False):
            ep_data = {"is_local": True}
        elif _cache_key == ms.ep_cache_key and ms.ep_cache_data:
            ep_data = ms.ep_cache_data
        else:
            app_core.info(f"[{p_name}] Requesting {playback_mod._fmt_ep(current_ep_label)} metadata...")
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
            playback_mod._clear_episode_source_state(ms)
            p_name = (ui.ui_show_ctx.get("_provider_name") or (ui.ui_show_ctx.get("_provider") or "").title() or "this provider") if ui.ui_show_ctx else "this provider"
            if ttype == "dub":
                msg = f"No DUB stream available for {playback_mod._fmt_ep(current_ep_label)} on {p_name}."
            else:
                msg = f"No stream available for {playback_mod._fmt_ep(current_ep_label)} on {p_name}."
            app_core.set_action_feedback(
                ui.ui_show_ctx,
                msg,
            )
            return "ACTION_MENU"

        first_source_name = None
        if ms.selected_stream is None:
            app_core._clear_streams()

            _ipc_player = app_core._ipc_player
            if getattr(ms, "_is_downloads", False):
                filepath = ms._download_files.get(str(ms.current_ep))
                if filepath:
                    res = ({"link": filepath, "resolution": "Local"}, "Local File", filepath, [])
                else:
                    res = None
            else:
                local_file = app_core.find_offline_file_for_episode(ms.show_title, ms.current_ep, cfg) if not getattr(args, 'download', False) and not getattr(args, 'sources', False) else None
                if local_file and os.path.exists(local_file):
                    res = ({"link": local_file, "resolution": "Offline (Local)", "is_local": True}, "Local File", local_file, [])
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
                        ep_data=ep_data,
                    )

            if res:
                ms.selected_stream, first_source_name, _, streams = res
                app_core._extend_streams(streams)
                if not getattr(args, 'download', False) and not getattr(args, 'print_url', False) and not (args.sources and not ui.initial_sources_prompted):
                    stream_name = ms.selected_stream.get("source_name", first_source_name or "Stream")
                    resolution = ms.selected_stream.get("resolution", "")
                    res_str = f" ({resolution})" if resolution else ""

                    aniskip_enabled = getattr(args, "aniskip", None)
                    if aniskip_enabled is None:
                        aniskip_enabled = cfg.get("aniskip", cfg.get("aniskip_enabled", True))

                    if aniskip_enabled:
                        action_show = ui.ui_show_ctx or {}
                        mal_id = app_core.get_show_mal_id(action_show)
                        ep_num = episode_progress_number(ms.current_ep)
                        if mal_id:
                            from ..media.aniskip import fetch_skip_times
                            skips = fetch_skip_times(mal_id, ep_num)
                            if skips:
                                from ..ui.player_screen import _fmt_time
                                skip_parts = [f"{s['label']} ({_fmt_time(s['start'])} → {_fmt_time(s['end'])})" for s in skips]
                                skip_summary = " · ".join(skip_parts)
                                skip_msg = f"\033[38;5;120m✔ AniSkip: {skip_summary}\033[0m"
                            else:
                                skip_msg = f"\033[38;5;244m• AniSkip: No skip times found for EP {ep_num}\033[0m"
                        else:
                            skip_msg = "\033[38;5;244m• AniSkip: No MAL ID available for this title\033[0m"

                        if skip_msg not in _player_ui_state["status_lines"]:
                            if _player_ui_state["status_lines"] and _player_ui_state["status_lines"][-1] != "":
                                _player_ui_state["status_lines"].append("")
                            _player_ui_state["status_lines"].append(skip_msg)
                            try:
                                from ..ui.player_screen import render as _render
                                _render(poster_manager=getattr(app_core, "_poster_manager", None), ui=ui)
                            except Exception:
                                pass

                    if app_core.is_termux() and aniskip_enabled:
                        if not cfg.get("aniskip_android_hint_dismissed", False) and not getattr(ui, "aniskip_android_hint_shown", False):
                            ui.aniskip_android_hint_shown = True
                            try:
                                from ..ui.player_screen import stop_loading_ticker
                                stop_loading_ticker()
                            except Exception:
                                pass

                            sys.stdout.write("\033[?1049h\033[2J\033[H\033[?25h")
                            sys.stdout.flush()

                            orig_termios = None
                            try:
                                if sys.stdin.isatty():
                                    import termios
                                    orig_termios = termios.tcgetattr(sys.stdin.fileno())
                                    from ..ui.display import _INITIAL_TERMIOS_ATTRS
                                    if _INITIAL_TERMIOS_ATTRS is not None:
                                        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
                                        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, _INITIAL_TERMIOS_ATTRS)
                            except Exception:
                                pass

                            print("\033[1;36mAniSkip on Android (MPV)\033[0m\n")
                            print("  \033[38;5;250m• Auto-skip is not supported via Android intents.\033[0m")
                            print("  \033[38;5;250m• To view chapter marks on the seekbar, add this line to /storage/emulated/0/Mpv/mpv.conf:\033[0m")
                            print("    \033[1;33mchapters-file=/storage/emulated/0/Mpv/chapters.txt\033[0m\n")

                            try:
                                choice = input("\033[1;97m[y = Don't show again, n = Disable AniSkip, s = Skip for now] (s): \033[0m").strip().lower()
                            except (EOFError, KeyboardInterrupt):
                                choice = "s"

                            if choice in ("y", "yes"):
                                cfg["aniskip_android_hint_dismissed"] = True
                                app_core.save_config(cfg)
                            elif choice in ("n", "no"):
                                cfg["aniskip"] = False
                                cfg["aniskip_enabled"] = False
                                aniskip_enabled = False
                                app_core.save_config(cfg)


                            try:
                                if sys.stdin.isatty() and orig_termios is not None:
                                    import termios
                                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, orig_termios)
                            except Exception:
                                pass

                            sys.stdout.write("\033[2J\033[H\033[?25l")
                            sys.stdout.flush()
                            try:
                                from ..ui.player_screen import render as _render
                                _render(poster_manager=getattr(app_core, "_poster_manager", None), ui=ui)
                            except Exception:
                                pass

                    if not is_download_mode:
                        for sec in (3, 2, 1):
                            _player_ui_state["countdown_message"] = f"\033[1;92m▶ Starting '{stream_name}'{res_str} in {sec}s ...\033[0m"
                            try:
                                from ..ui.player_screen import render as _render
                                _render(poster_manager=getattr(app_core, "_poster_manager", None), ui=ui)
                            except Exception:
                                pass
                            time.sleep(1)
                        _player_ui_state["countdown_message"] = ""


        if args.sources and not ui.initial_sources_prompted:
            ui.initial_sources_prompted = True
            if first_source_name is not None:
                app_core.start_bg_resolve(ep_data, {first_source_name})
            app_core._exit_player_screen()
            return "MIRRORS"

        if ms.selected_stream is None:
            app_core._exit_player_screen()
            playback_mod._clear_episode_source_state(ms)
            p_name = (ui.ui_show_ctx.get("_provider_name") or (ui.ui_show_ctx.get("_provider") or "").title() or "this provider") if ui.ui_show_ctx else "this provider"
            ep_label = playback_mod._display_episode_label(ui.ui_show_ctx, ms.current_ep, ttype)
            if ttype == "dub":
                msg = f"No DUB stream available for {playback_mod._fmt_ep(ep_label)} on {p_name}."
            else:
                msg = f"No stream available for {playback_mod._fmt_ep(ep_label)} on {p_name}."
            app_core.set_action_feedback(
                ui.ui_show_ctx,
                msg,
            )
            return "ACTION_MENU"

    if args.print_url:
        app_core._exit_player_screen(close_alt=True)
        print(ms.selected_stream["link"])
        audio_url = ms.selected_stream.get("audio_url", "")
        if audio_url:
            print(f"Audio: {audio_url}")
        sub_url = ms.selected_stream.get("subtitle_url", "")
        if sub_url:
            print(f"Subtitle: {sub_url}")
        subtitles = ms.selected_stream.get("subtitles") or ms.selected_stream.get("vtt") or []
        if isinstance(subtitles, list) and len(subtitles) > 1:
            for sub in subtitles:
                s_url = sub.get("url") or sub.get("file")
                s_lbl = sub.get("label", "Unknown")
                if s_url and s_url != sub_url:
                    print(f"Subtitle ({s_lbl}): {s_url}")
        ref = ms.selected_stream.get("referer", "")
        if ref:
            print(f"Referer: {ref}")
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
                ms.show_title, current_ep_label, ms.selected_stream, 
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
                    
                    def build_offline_metadata(s):
                        meta = {}
                        keys_to_keep = [
                            "id", "name", "englishName", "nativeName", "altNames",
                            "thumbnail", "description", "type", "format",
                            "status", "season", "airedStart", "airedEnd", "startDate",
                            "endDate", "score", "genres", "tags", "aniListId", "malId",
                            "_display_name", "_display_english_name", "_anilist_list",
                            "_anilist_progress", "_anilist_score", "anilistMatch",
                            "originalEpisodeCount"
                        ]
                        for k in keys_to_keep:
                            if k in s:
                                meta[k] = s[k]
                        if "originalEpisodeCount" not in meta and "episodeCount" in s:
                            meta["originalEpisodeCount"] = s["episodeCount"]
                        return meta
                        
                    db["shows"][title]["metadata"] = build_offline_metadata(s_ctx)
                    ep_str = str(ms.current_ep)
                    if ep_str not in db["shows"][title]["episodes"]:
                        db["shows"][title]["episodes"].append(ep_str)
                    save_downloads_db(db)
                except Exception:
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
                exclude_sources=exclude_sources,
                ep_data=ep_data,
            )
            if not res:
                break
            ms.selected_stream, first_source_name, _, streams = res
            app_core._extend_streams(streams)

        if not download_ok:
            print(f"\n{RED}All mirrors failed for EP {current_ep_label}. Skipping to next episode...{RESET}")

        download_batch_end = ms.download_batch_end if ms.download_batch_end is not None else current_ep_label
        try:
            is_less = int(float(str(download_batch_end))) > int(float(str(current_ep_label)))
        except ValueError:
            is_less = ms.current_ep_index < (ms.total_eps - 1)

        if is_less and ms.current_ep_index + 1 < ms.total_eps:
            ms.current_ep_index += 1
            ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
            ms.selected_stream = None
            app_core._clear_streams()
            return "PLAY"
        else:
            print(f"\n{GREEN}Downloads complete.{RESET}")
            if getattr(args, "_from_action_menu_download", False):
                if download_ok:
                    app_core.set_action_feedback(ui.ui_show_ctx, f"✔ Downloaded {playback_mod._fmt_ep(current_ep_label)}")
                else:
                    app_core.set_action_feedback(ui.ui_show_ctx, f"✖ Download failed for {playback_mod._fmt_ep(current_ep_label)}")
                args.download = False
                args._from_action_menu_download = False
                time.sleep(1.0)
                return ui.action_prev_state or "ACTION_MENU"
            return "QUIT"



    # ── Launch player ─────────────────────────────────────────────
    def fetch_cb(ep_num):
        if isinstance(ep_num, int) and 1 <= ep_num <= len(episode_ids):
            ep_idx = ep_num - 1
        else:
            ep_idx = episode_index_for_id(
                episode_ids, ep_num, labels=ui.ui_show_ctx.get("_episode_labels")
            )
        if ep_idx is None:
            return None
            
        target_ep = episode_id_at(episode_ids, ep_idx)
        if getattr(ms, "_is_downloads", False):
            filepath = ms._download_files.get(str(target_ep))
            if filepath:
                return ({"link": filepath, "resolution": "Local"}, "Local File", filepath, [])
            return None
            
        return app_core.fetch_episode_stream(
            ms.show_id,
            target_ep,
            ttype,
            cfg.get("quality", "best"),
            provider_id=provider_id,
        )

    is_binge = args.binge or cfg.get("binge", False)

    if app_core.is_termux():
        player = args.player or cfg.get("player", "mpvrex" if app_core.pkg_installed("xyz.mpv.rex") and not app_core.pkg_installed("is.xyz.mpv") else "mpv")
        if player == "mpv" and not args.player:
            if not app_core.pkg_installed("is.xyz.mpv") and app_core.pkg_installed("xyz.mpv.rex"):
                player = "mpvrex"

        aniskip_enabled = getattr(args, "aniskip", None)
        if aniskip_enabled is None:
            aniskip_enabled = cfg.get("aniskip", cfg.get("aniskip_enabled", True))

        action_show = ui.ui_show_ctx or {}
        mal_id = app_core.get_show_mal_id(action_show)

        result = app_core.play_android(
            ms.show_title,
            current_ep_label,
            ms.selected_stream,
            fetch_cb,
            player,
            ms.total_eps,
            ms.show_id,
            is_binge,
            mal_id=mal_id,
            aniskip_enabled=aniskip_enabled,
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

        app_core._exit_player_screen()
        return "ACTION_MENU"

    else:
        if first_source_name is not None:
            exclude = {first_source_name}
            app_core.start_bg_resolve(ep_data, exclude)

        next_episode = episode_id_at(episode_ids, ms.current_ep_index + 1) if ms.current_ep_index + 1 < ms.total_eps else None

        aniskip_enabled = getattr(args, "aniskip", None)
        if aniskip_enabled is None:
            aniskip_enabled = cfg.get("aniskip", cfg.get("aniskip_enabled", True))

        aniskip_auto = getattr(args, "auto_skip", None)
        if aniskip_auto is None:
            aniskip_auto = cfg.get("auto_skip", cfg.get("aniskip_auto", True))


        action_show = ui.ui_show_ctx or {}
        mal_id = app_core.get_show_mal_id(action_show)

        result, percent, time_pos, duration, played_seconds = app_core.play_desktop(
            ms.show_title, current_ep_label, ms.selected_stream, fetch_cb,
            ms.total_eps, is_binge, ms.show_id, ms.pending_osd_msg,
            ms.current_ep_index, next_episode,
            mal_id=mal_id, aniskip_enabled=aniskip_enabled, aniskip_auto=aniskip_auto
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
            sync_pending = resolve_tracking_fn(ui.search_prev_state, args, cfg, ui.ui_show_ctx)

            if sync_pending:
                tkn = cfg.get("anilist_token")
                if tkn and pending_progress:
                    show_ctx = ui.ui_show_ctx
                    new_status = tracking_status_for_progress(show_ctx, pending_progress)

                    def _pending_sync_success(ep=pending_ep, ctx=show_ctx):
                        app_core.set_action_feedback(ctx, f"✔ Synced EP {ep} to AniList")
                    def _pending_sync_failure(ctx=show_ctx):
                        app_core.set_action_feedback(ctx, "Saved offline • AniList sync pending")

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
                        app_core.set_action_feedback(show_ctx, f"Sync queued: EP {pending_ep}")
                else:
                    sync_pending = False

            if not sync_pending:
                app_core.save_resume_time(ms.show_id, pending_ep, 0)
                app_core.clear_pending_completion(ms.show_id)

        should_update_history = (
            not sync_enabled
            and not getattr(ms, "_is_downloads", False)
            and playback_updates_history(
            result, percent, time_pos, duration, played_seconds
            )
        )
        if should_update_history:
            app_core.save_history(ui.ui_show_ctx, ms.current_ep, ttype)
            
        if getattr(ms, "_is_downloads", False) and playback_updates_history(
            result, percent, time_pos, duration, played_seconds
        ):
            try:
                from allmanga_cli.core.storage import update_offline_watch_status
                folder_name = ui.ui_show_ctx.get("_folder_name", ms.show_title)
                if update_offline_watch_status(folder_name, ms.current_ep):
                    watched = ui.ui_show_ctx.get("watched_episodes", [])
                    if str(ms.current_ep) not in watched:
                        watched.append(str(ms.current_ep))
                    ui.ui_show_ctx["watched_episodes"] = watched
            except Exception:
                pass

        if auto_scrobbled:
            app_core.save_resume_time(ms.show_id, ms.current_ep, 0)
        elif time_pos > 30:
            app_core.save_resume_time(ms.show_id, ms.current_ep, time_pos)

        if result == "QUIT" or result == "EOF":
            if auto_scrobbled and resolve_tracking_fn(ui.search_prev_state, args, cfg, ui.ui_show_ctx):
                tkn = cfg.get("anilist_token")
                if tkn:
                    show_ctx = ui.ui_show_ctx
                    progress_ep = episode_progress_number(ms.current_ep, ms.current_ep_index + 1)
                    new_status = tracking_status_for_progress(show_ctx, progress_ep)
                    queued = app_core.queue_anilist_progress(
                        tkn, ms.show_title, progress_ep, al_id,
                        show_ctx, ttype, new_status,
                        on_success=lambda ep=ms.current_ep, ctx=show_ctx:
                            app_core.set_action_feedback(ctx, f"✔ Synced EP {ep} to AniList"),
                        on_failure=lambda ctx=show_ctx:
                            app_core.set_action_feedback(ctx, "Saved offline • AniList sync pending"),
                    )
                    if queued:
                        app_core.set_action_feedback(show_ctx, f"Sync queued: EP {ms.current_ep}")

            if result == "EOF" and (args.binge or cfg.get("binge")):
                if ms.current_ep_index + 1 < ms.total_eps:
                    next_ep = episode_id_at(episode_ids, ms.current_ep_index + 1)
                    if flags.incognito_mode:
                        ms.pending_osd_msg = None
                    elif auto_scrobbled:
                        ms.pending_osd_msg = marked_watched_osd(
                            ms.current_ep,
                            resolve_tracking_fn(ui.search_prev_state, args, cfg, ui.ui_show_ctx)
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
                elif auto_scrobbled and resolve_tracking_fn(ui.search_prev_state, args, cfg, ui.ui_show_ctx):
                    tkn = cfg.get("anilist_token")
                    if tkn:
                        show_ctx = ui.ui_show_ctx
                        progress_ep = episode_progress_number(ms.current_ep, ms.current_ep_index + 1)
                        new_status = tracking_status_for_progress(show_ctx, progress_ep)
                        queued = app_core.queue_anilist_progress(
                            tkn, ms.show_title, progress_ep, al_id,
                            show_ctx, ttype, new_status,
                            on_success=lambda ep=ms.current_ep, ctx=show_ctx:

                                app_core.set_action_feedback(ctx, f"✔ Synced EP {ep} to AniList"),
                            on_failure=lambda ctx=show_ctx:
                                app_core.set_action_feedback(ctx, "Saved offline • AniList sync pending"),
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
