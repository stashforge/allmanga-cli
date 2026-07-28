import os
import shutil
import re

from ..core.storage import load_downloads_db, save_downloads_db, get_default_download_dir, load_config, save_config

from ..app_core import build_info_panel, _get_poster, set_ui_context, warn, info
from ..ui.picker import tui_pick
from ..ui.help import picker_help
from ..core.terminal import truncate_display as _truncate_display
_C_HINT = "\033[38;5;244m"
_RST = "\033[0m"
def handle_downloads_state(flags, ui, ms, cfg, args, ttype, resolveTracking):
    db = load_downloads_db()
    
    download_dir = cfg.get("download_dir", "")
    if not download_dir:
        download_dir = get_default_download_dir()
        live_cfg = load_config()
        live_cfg["download_dir"] = download_dir
        save_config(live_cfg)
        
    download_dir = os.path.expanduser(download_dir)
    shows = db.get("shows", {})
    
    dirty = False
    valid_titles = []
    
    for title, data in list(shows.items()):
        folder_path = os.path.join(download_dir, title)
        if not os.path.isdir(folder_path):
            del shows[title]
            dirty = True
            continue
            
        meta = data.get("metadata", {})
        if "_id" not in meta and "availableEpisodes" not in meta:
            # User requested not to auto-fetch metadata because title match is hard and causes delays
            meta["name"] = title
            data["metadata"] = meta
            dirty = True
                
        try:
            actual_files = os.listdir(folder_path)
        except OSError:
            actual_files = []
            
        valid_eps = []
        for ep in data.get("episodes", []):
            ep_pattern = re.compile(rf"(^|[^0-9]){ep}([^0-9]|$)")
            if any(ep_pattern.search(f) for f in actual_files):
                valid_eps.append(ep)
                
        if len(valid_eps) != len(data.get("episodes", [])):
            data["episodes"] = valid_eps
            dirty = True
            
        meta = data.get("metadata", {})
        if meta.get("episodeCount") != len(valid_eps):
            meta["episodeCount"] = len(valid_eps)
            data["metadata"] = meta
            dirty = True
            
        if not valid_eps:
            del shows[title]
            dirty = True
            try:
                os.rmdir(folder_path)
            except OSError:
                pass
        else:
            valid_titles.append((title, data))
            
    if dirty:
        save_downloads_db(db)

    # Discovery scan: auto-import folders on disk that aren't tracked in the DB
    VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.ts')
    EP_NUM_RE = re.compile(r'Episode\s+(\d+)', re.IGNORECASE)
    if os.path.isdir(download_dir):
        for folder_name in os.listdir(download_dir):
            folder_path = os.path.join(download_dir, folder_name)
            if not os.path.isdir(folder_path) or folder_name in shows:
                continue
            try:
                files = [f for f in os.listdir(folder_path) if f.endswith(VIDEO_EXTS)]
            except OSError:
                continue
            if not files:
                continue
            episodes = []
            for f in files:
                m = EP_NUM_RE.search(f)
                if m:
                    episodes.append(m.group(1))
                    
            # Try to fetch real metadata for the discovered folder
            metadata = {"name": folder_name, "episodeCount": len(episodes)}
            
            data = {"metadata": metadata, "episodes": sorted(episodes, key=lambda e: int(e))}
            shows[folder_name] = data
            valid_titles.append((folder_name, data))
            dirty = True
        if dirty:
            save_downloads_db(db)

    if not valid_titles:
        warn(f"No downloaded videos found in {download_dir}.")
        return "QUIT"

    def _build_folder_opts():
        return [f"{title}  ({len(data.get('episodes', []))})" for title, data in valid_titles]

    folder_opts = _build_folder_opts()

    def _folders_hdr(si):
        try:
            w = os.get_terminal_size().columns
        except OSError:
            w = 80
        parts = []
        if 0 <= si < len(valid_titles):
            title, data = valid_titles[si]
            show = data.get("metadata", {})
            show["watched_episodes"] = data.get("watched_episodes", [])
            show["_folder_name"] = title
            build_info_panel(show, "sub", w, parts, local_only=True)
            
        line = f"Downloaded anime  │  {download_dir}  │  Enter=episodes  Del=delete title  Esc=quit"
        parts.append(f"{_C_HINT}{_truncate_display(line, max(1, w - 1))}{_RST}")
        return "\n".join(parts)
        
    def _folders_top_hdr(si):
        if 0 <= si < len(valid_titles):
            title, data = valid_titles[si]
            show = data.get("metadata", {})
            ui.hovered_show_id = show.get("_id")
            ui.hovered_show_obj = show
            import allmanga_cli.app_core as core
            core._hovered_show_id = ui.hovered_show_id
            poster = _get_poster(show)
            if poster:
                return poster
        return ""
        
    def _delete_title(si):
        nonlocal valid_titles, folder_opts, db
        if 0 <= si < len(valid_titles):
            title, data = valid_titles[si]
            folder_path = os.path.join(download_dir, title)
            if os.path.isdir(folder_path):
                shutil.rmtree(folder_path, ignore_errors=True)
            if title in db["shows"]:
                del db["shows"][title]
            save_downloads_db(db)
            valid_titles.pop(si)
            folder_opts = _build_folder_opts()
        return folder_opts, _folders_hdr(0)

    folder_idx = tui_pick(
        flags, ui, "Downloads", folder_opts,
        header_fn=_folders_hdr,
        top_header_fn=_folders_top_hdr,
        delete_fn=_delete_title,
        help_dict=picker_help("Open details", "Quit", "Quit", delete_label="Delete title")
    )
    if folder_idx < 0:
        return "QUIT"

    title, data = valid_titles[folder_idx]
    folder_path = os.path.join(download_dir, title)
    try:
        raw_files = os.listdir(folder_path)
        files = [os.path.join(folder_path, f) for f in raw_files if f.endswith(VIDEO_EXTS)]
        files.sort()
    except OSError:
        files = []
        
    if not files:
        warn(f"No downloaded videos found in {title}.")
        return "DOWNLOADS"

    # Inject episodes into show metadata so the streaming UI can read them
    show = data.get("metadata", {})
    episodes_list = []
    
    ms._download_files = {} # map ep_str -> filepath
    for filepath in files:
        basename = os.path.basename(filepath)
        m = EP_NUM_RE.search(basename)
        ep_str = m.group(1) if m else basename
        episodes_list.append(ep_str)
        ms._download_files[ep_str] = filepath

    if "availableEpisodesDetail" not in show:
        show["availableEpisodesDetail"] = {}
        
    show["availableEpisodesDetail"][ttype] = episodes_list
    show["availableEpisodes"] = {ttype: len(episodes_list)}
    show["episodeCount"] = len(episodes_list)
    show["_folder_name"] = title
    
    # Force the episode catalog to match only what's downloaded
    # (Overrides any stale cache from previous auto-fetches)
    show["_episode_ids"] = episodes_list
    show["_episode_ids_ttype"] = ttype
    show["_episode_catalog_state"] = "loaded"
    
    # Setup state machine variables for the selected offline anime
    ms._is_downloads = True
    ms._download_dir = folder_path
    ms.show_title = title
    ms.show_id = show.get("_id")
    set_ui_context(ui, show, ttype)
    ui.search_prev_state = "DOWNLOADS"
    
    return "DETAILS"
