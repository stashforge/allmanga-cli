"""Main application orchestrator and state-machine coordinator."""

from __future__ import annotations

import os
import sys
import json
import time
import signal
import shutil
from typing import Any

from ..context import FLAGS as runtime_flags, UiState, MachineState
from ..cli.args import parse_cli_args
from ..cli.completion import generate_completion, install_completion
from ..core.api import SearchFailure
from ..core.storage import (
    load_config,
    save_config,
    load_downloads_db,
    save_downloads_db,
    load_history,
    load_search_history,
    clear_search_history,
    get_default_download_dir,
    get_title_sync,
)
from ..core.anilist import (
    clear_anilist_token,
    save_anilist_token,
    prompt_anilist_token,
    anilist_token_storage_status,
    anilist_auth_status_lines,
    anilist_auth_token_lines,
    anilist_auth_login_existing_lines,
    retry_queued_anilist_writes,
    fetch_anilist_list,
    search_anilist,
    get_show_anilist_id,
)
from ..providers import (
    _DEFAULT_PROVIDER_ID,
    available_providers,
    get_provider_registry,
    provider_key,
)
from ..domain.metadata import prepare_show_display_state
from ..domain.titles import get_show_display_title
from ..domain.episodes import episode_id_at, episode_index_for_id
from ..ui import display
from ..ui.display import restore_terminal
from ..ui.terminal_images import clear_now as clear_terminal_images_now
from ..playback.mpv import MpvIpc
from ..core.processes import (
    register_subprocess,
    unregister_subprocess,
    kill_active_subprocesses,
)
import allmanga_cli.app as handlers


def trigger_migration(old_dir_full: str, new_dir: str) -> None:
    db = load_downloads_db()
    if os.path.isdir(old_dir_full) and os.path.abspath(old_dir_full) != os.path.abspath(new_dir):
        ans = input(f"Move existing downloads from {old_dir_full} to {new_dir}? [y/N]: ").strip().lower()
        if ans == "y":
            print(f"Moving downloads to {new_dir}...")
            try:
                os.makedirs(new_dir, exist_ok=True)
                moved_anything = False
                shows = db.get("shows", {})
                for title in shows.keys():
                    s = os.path.join(old_dir_full, title)
                    d = os.path.join(new_dir, title)
                    if os.path.isdir(s):
                        shutil.move(s, d)
                        moved_anything = True
                
                if moved_anything and os.path.basename(old_dir_full.rstrip(os.sep)) == "allmanga-cli":
                    try:
                        os.rmdir(old_dir_full)
                        print(f"Cleaned up empty folder: {old_dir_full}")
                    except OSError:
                        pass
                        
                print("Migration complete!")
            except Exception as e:
                print(f"Failed to migrate files: {e}", file=sys.stderr)


def handle_config_command(args: Any) -> None:
    cfg = load_config()
    if args.config_action == "set":
        key = args.config_key
        val = args.config_value
        
        if key == "download_dir":
            old_dir = cfg.get("download_dir", "")
            new_dir = os.path.expanduser(str(val or "").strip())
            
            if not new_dir:
                print("download_dir requires a value.", file=sys.stderr)
                return
                
            if not new_dir.endswith("allmanga-cli"):
                ans_append = input(f"Create 'allmanga-cli' subfolder in {new_dir}? [Y/n]: ").strip().lower()
                if ans_append != 'n':
                    new_dir = os.path.join(new_dir, "allmanga-cli")
                    val = os.path.join(str(val or "").strip(), "allmanga-cli")
            
            if not old_dir:
                old_dir_full = get_default_download_dir()
            else:
                old_dir_full = os.path.expanduser(old_dir)
                
            trigger_migration(old_dir_full, new_dir)
            cfg["download_dir"] = val
            save_config(cfg)
            db = load_downloads_db()
            db["current_download_dir"] = new_dir
            save_downloads_db(db)
            print(f"Config updated: {key} = {val}")
        else:
            cfg[key] = val
            save_config(cfg)
            print(f"Config updated: {key} = {val}")


def main() -> None:
    from .. import app_core
    def _force_exit(sig, frame):
        kill_active_subprocesses()
        try:
            restore_terminal()
        except Exception:
            pass
        os._exit(130)
            
    signal.signal(signal.SIGINT, _force_exit)

    args, pa = parse_cli_args()
    
    if not getattr(args, "config_action", None):
        cfg = load_config()
        db = load_downloads_db()
        current_cfg_dir = cfg.get("download_dir", "")
        if current_cfg_dir:
            current_cfg_dir_full = os.path.expanduser(current_cfg_dir)
            db_dir_full = db.get("current_download_dir", "")
            if db_dir_full and os.path.abspath(db_dir_full) != os.path.abspath(current_cfg_dir_full):
                print(f"\n\033[93m[!] Detected download directory change in config from {db_dir_full} to {current_cfg_dir_full}\033[0m")
                globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
                trigger_migration(db_dir_full, current_cfg_dir_full)
            
            if db.get("current_download_dir") != current_cfg_dir_full:
                db["current_download_dir"] = current_cfg_dir_full
                save_downloads_db(db)
                
    if getattr(args, "completion_shell", None):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        if getattr(args, "completion_install", False):
            path = install_completion(args.completion_shell)
            print(f"Installed {args.completion_shell} completion:")
            print(path)
            if args.completion_shell == "bash":
                print("Restart your shell, or run: exec bash")
            elif args.completion_shell == "zsh":
                print("Ensure ~/.zfunc is in fpath, then run: compinit")
            elif args.completion_shell == "fish":
                print("Restart fish, or run: exec fish")
            return
        print(generate_completion(args.completion_shell), end="")
        return

    if getattr(args, "show_search_history", False):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        for query in load_search_history():
            print(query)
        return

    if getattr(args, "clear_search_history", False):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        clear_search_history()
        print("Search history cleared.")
        return

    if getattr(args, "config_action", None):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        handle_config_command(args)
        return

    if getattr(args, "list_providers", False):
        globals()["SUPPRESS_FINAL_CURSOR_RESTORE"] = True
        cfg = load_config()
        default_pid = cfg.get("provider", _DEFAULT_PROVIDER_ID)
        CYAN, GREEN, BOLD, RESET, RED, YELLOW, DIM = "\033[36m", "\033[32m", "\033[1m", "\033[0m", "\033[31m", "\033[33m", "\033[2m"
        registry = get_provider_registry()
        
        print(f"\n{BOLD}Available Streaming Providers:{RESET}\n")
        term_width = shutil.get_terminal_size((80, 20)).columns

        rows = []
        for pid in sorted(available_providers().keys()):
            meta = registry.get(pid, {})
            name = meta.get("name", pid.title())
            engine = meta.get("engine", "unknown")
            status = meta.get("status", "unknown")
            ptype = meta.get("type", "anime")
            langs = "/".join(meta.get("languages", ["sub"]))
            rows.append({"pid": pid, "name": name, "engine": engine, "status": status, "type": ptype, "langs": langs})
            
        w_id = max(max((len(r["pid"]) + 2 for r in rows), default=0), len("ID"))
        w_name = max(max((len(r["name"]) for r in rows), default=0), len("Name"))
        w_eng = max(max((len(r["engine"]) for r in rows), default=0), len("Engine"))
        w_stat = max(max((len(r["status"]) for r in rows), default=0), len("Status"))
        w_type = max(max((len(r["type"]) for r in rows), default=0), len("Type"))
        w_lang = max(max((len(r["langs"]) for r in rows), default=0), len("Languages"))
        
        spacing = 4
        show_type = True
        show_name = True
        show_engine = True
        
        def calc_total_len():
            l = 2 + w_id + spacing + w_stat + spacing + w_lang
            if show_name: l += w_name + spacing
            if show_engine: l += w_eng + spacing
            if show_type: l += w_type + spacing
            return l

        if calc_total_len() > term_width:
            show_type = False
        if calc_total_len() > term_width:
            show_name = False
        if calc_total_len() > term_width:
            show_engine = False
        
        header = f"    {BOLD}{'ID'.ljust(w_id - 2 + spacing)}"
        if show_name: header += f"{'Name'.ljust(w_name + spacing)}"
        if show_engine: header += f"{'Engine'.ljust(w_eng + spacing)}"
        header += f"{'Status'.ljust(w_stat + spacing)}"
        if show_type: header += f"{'Type'.ljust(w_type + spacing)}"
        header += f"{'Languages'}{RESET}"
        
        print(header)
        print(f"  {DIM}{'-'*calc_total_len()}{RESET}")
        
        for r in rows:
            pid, name, engine, status, ptype, langs = r["pid"], r["name"], r["engine"], r["status"], r["type"], r["langs"]
            status_color = GREEN if status == "active" else RED
            
            if pid == default_pid:
                id_str = f"{GREEN}▸ {pid.ljust(w_id - 2)}{RESET}"
            else:
                id_str = f"  {CYAN}{pid.ljust(w_id - 2)}{RESET}"
                
            row_str = f"  {id_str}{' '*spacing}"
            if show_name: row_str += f"{name.ljust(w_name)}{' '*spacing}"
            
            if show_engine:
                engine_str = f"{YELLOW}{engine.ljust(w_eng)}{RESET}" if engine == "hybrid" else f"{engine.ljust(w_eng)}"
                if engine == "scraper": engine_str = f"{DIM}{engine.ljust(w_eng)}{RESET}"
                row_str += f"{engine_str}{' '*spacing}"
                
            row_str += f"{status_color}{status.ljust(w_stat)}{RESET}{' '*spacing}"
            if show_type: row_str += f"{ptype.ljust(w_type)}{' '*spacing}"
            row_str += f"{langs}"
            
            print(row_str)
        
        print()
        print(f"  {DIM}Note: Scrapers are brittle and may break often. APIs and Hybrids are recommended.{RESET}\n")
        return

    app_core.check_deps()
    cfg = load_config()
    if getattr(args, "provider", None) is None:
        args.provider = cfg.get("provider", _DEFAULT_PROVIDER_ID)
    display._configure_spinner_from_config(cfg)

    runtime_flags.debug_mode = args.debug
    runtime_flags.incognito_mode = bool(args.incognito)
    if args.incognito and (args.download or args.downloads or args.login or args.logout):
        pa.error("--incognito cannot be combined with downloads, login, or logout")
    if args.incognito:
        args.no_sync = True
    runtime_flags.sync_force_on = bool(args.sync and not args.no_sync)
    runtime_flags.sync_force_off = bool(args.no_sync)
    if getattr(args, "cover", None) is not None:
        runtime_flags.show_image = bool(args.cover)
    else:
        runtime_flags.show_image = bool(cfg.get("cover", False))

    if args.json:
        q = " ".join(args.query)
        ttype = "dub" if args.dub else "sub"

        if args.anilist is not None:
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
                res = app_core.search_anime(
                    q,
                    ttype,
                    provider_id=args.provider,
                )
                print(json.dumps(res, indent=2))
        sys.exit(0)

    if args.logout:
        clear_anilist_token(cfg)
        print(f"\033[32mLogged out of AniList.\033[0m")
        sys.exit(0)

    if getattr(args, "auth_status", False):
        print("\n".join(anilist_auth_status_lines(cfg)))
        sys.exit(0)

    if getattr(args, "auth_token", False):
        lines = anilist_auth_token_lines(cfg, raw=getattr(args, "auth_token_raw", False))
        if not lines:
            print("AniList token is not saved.", file=sys.stderr)
            sys.exit(1)
        print("\n".join(lines))
        sys.exit(0)

    if args.login:
        if anilist_token_storage_status(cfg) != "none":
            print("\n".join(anilist_auth_login_existing_lines(cfg)))
            sys.exit(0)
        print(f"\n\033[33mAniList login\033[0m")
        print("Open this link, sign in, and copy the token:")
        print("\033[4mhttps://anilist.co/api/v2/oauth/authorize?client_id=9857&response_type=token\033[0m")
        tkn = prompt_anilist_token()
        if tkn:
            storage = save_anilist_token(cfg, tkn)
            print(f"\033[32mAniList token saved to {storage}.\033[0m")
        else:
            print(f"\033[31mNo token provided.\033[0m")
        sys.exit(0)

    runtime_flags.spinner_style = display._spinner_style
    flags = runtime_flags
    ui = UiState()

    def warn_before_tui(message):
        print(f"\n\033[33m{message}\033[0m")
        for remaining in range(3, 0, -1):
            print(f"\rContinuing in {remaining}...", end="", flush=True)
            time.sleep(1)
        print("\rContinuing now.   ")

    if args.sync and not args.no_sync:
        if args.history or args.cont:
            warn_before_tui(
                "--sync only applies to searched titles. History and continue stay local."
            )
            args.sync = False
            flags.sync_force_on = False
        elif not cfg.get("anilist_token") and not args.anilist:
            warn_before_tui(
                "--sync needs AniList login. Sync is disabled for this session."
            )
            args.sync = False
            args.no_sync = True
            flags.sync_force_on = False
            flags.sync_force_off = True

    def resolveTracking(ctx, args, cfg, show=None):
        show = show or app_core.get_ui_show(ui)

        if getattr(args, "no_sync", False) or flags.incognito_mode:
            return False

        sync_flag = getattr(args, "sync", False)
        config_sync = bool(cfg.get("sync") or cfg.get("auto_track"))

        if (sync_flag or config_sync) and ctx == "SEARCH":
            return bool(cfg.get("anilist_token") and show and get_show_anilist_id(show))

        if ctx in ("ANILIST_BROWSE", "ANILIST_SEARCH", "ANILIST_AIRING"):
            return bool(cfg.get("anilist_token") and show and get_show_anilist_id(show))

        return False

    globals()["resolveTracking"] = resolveTracking

    if args.anilist and not args.no_sync and not cfg.get("anilist_token"):
        print(f"\n\033[33mAniList tracking needs a token.\033[0m")
        print("Open this link, sign in, and copy the token:")
        print("\033[4mhttps://anilist.co/api/v2/oauth/authorize?client_id=9857&response_type=token\033[0m")
        tkn = prompt_anilist_token()
        if tkn:
            storage = save_anilist_token(cfg, tkn)
            print(f"\033[32mAniList token saved to {storage}.\033[0m")
        else:
            print(f"\033[31mNo token provided. Tracking is disabled for this session.\033[0m")
            args.no_sync = True
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

    if getattr(args, "dub", False):
        ttype = "dub"
    elif getattr(args, "sub", False):
        ttype = "sub"
    else:
        ttype = cfg.get("translation_type", "sub")
    ui.ui_ttype_ctx = ttype
    active_provider = getattr(args, "provider", None) or cfg.get("provider") or cfg.get("default_provider") or _DEFAULT_PROVIDER_ID
    ui.ui_provider_ctx = provider_key(active_provider)
    quality = args.quality or cfg.get("quality","1080p")

    ms = MachineState(
        query_str=" ".join(args.query) if args.query else "",
        just_searched=bool(args.query),
        anilist_search_parent="QUIT",
        download_batch_end=globals().get("_download_batch_end")
    )

    state = "SEARCH"

    if args.anilist is not None:
        if args.anilist == "search":
            state = "ANILIST_SEARCH"
        elif args.anilist == "airing":
            state = "ANILIST_AIRING"
            args.anilist = "menu"
        else:
            if not cfg.get("anilist_token"):
                print(f"\n\033[33mAniList account is not linked.\033[0m")
                print(f"Run \033[1m./allmanga-cli --login\033[0m to authenticate.")
                sys.exit(1)
            state = "ANILIST_MENU"
    elif args.cont:
        hist = load_history()
        if hist:
            h = hist[0]
            show = h.get("show", {})
            prepare_show_display_state(show, h.get("translation_type", ttype))
            ms.show_id = show.get("_id")
            ms.show_title = get_show_display_title(show)
            _hist_ttype = h.get("translation_type", ttype)
            ms.total_eps = show.get("availableEpisodes", {}).get(_hist_ttype, 1)
            ms.current_ep = app_core.playback_ep_from_history_entry(h, _hist_ttype)
            episode_ids = app_core.ensure_episode_ids(show, _hist_ttype)
            ms.total_eps = len(episode_ids) or ms.total_eps
            ms.current_ep_index = episode_index_for_id(episode_ids, ms.current_ep)
            app_core.set_ui_context(ui, show, _hist_ttype)
            if not episode_ids:
                print(app_core.episode_catalog_error(show), file=sys.stderr)
                state = "HISTORY"
            elif ms.current_ep_index is None:
                print("Saved episode is not present in the current provider catalog.", file=sys.stderr)
                state = "HISTORY"
            else:
                ms.current_ep = episode_id_at(episode_ids, ms.current_ep_index)
                print(f"Continuing {ms.show_title}: EP {ms.current_ep}/{ms.total_eps}")
                state = "PLAY"
        else:
            print("Watch history is empty.")
    elif args.downloads:
        state = "DOWNLOADS"
    elif args.history:
        state = "HISTORY"

    while state != "QUIT":
        cur_ttype = ui.ui_ttype_ctx if ui.ui_ttype_ctx is not None else ttype
        if state == "DOWNLOADS":
            from allmanga_cli.app.downloads import handle_downloads_state
            state = handle_downloads_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "SEARCH":
            state = handlers.handle_search_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "HISTORY":
            state = handlers.handle_history_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "ANILIST_MENU":
            state = handlers.handle_anilist_menu_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "ANILIST_AIRING":
            state = handlers.handle_anilist_airing_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "ANILIST_BROWSE":
            state = handlers.handle_anilist_browse_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "ANILIST_SEARCH":
            state = handlers.handle_anilist_search_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "DETAILS":
            state = handlers.handle_details_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "UPDATE_PROGRESS":
            state = handlers.handle_update_progress_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "UPDATE_STATUS":
            state = handlers.handle_update_status_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "UPDATE_SCORE":
            state = handlers.handle_update_score_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "EPISODE":
            state = handlers.handle_episode_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "PLAY":
            state = handlers.handle_play_state(flags, ui, ms, cfg, args, cur_ttype, quality, resolveTracking)
        elif state == "ACTION_MENU":
            state = handlers.handle_action_menu_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        elif state == "MIRRORS":
            state = handlers.handle_mirrors_state(flags, ui, ms, cfg, args, cur_ttype, resolveTracking)
        else:
            print(f"Unknown state: {state}", file=sys.stderr)
            state = "QUIT"

    app_core._ipc_player.quit()
