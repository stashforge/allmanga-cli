import os
import re
import shutil

from .. import app_core
from ..app_core import _get_poster, _poster_footer_line, build_info_panel, make_info_fn, set_ui_context, warn
from ..core.storage import get_default_download_dir, load_config, load_downloads_db, save_config, save_downloads_db
from ..core.terminal import truncate_display as _truncate_display
from ..ui.help import picker_help
from ..ui.picker import tui_pick

_C_HINT = "\033[38;5;244m"
_RST = "\033[0m"
VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.ts', '.webm')


def extract_offline_episode_info(filepath: str) -> tuple[float, float, str, str]:
    """Extract (primary_num, secondary_num, clean_ep_id, raw_label) from filepath."""
    stem = os.path.splitext(os.path.basename(filepath))[0]
    m = re.search(r'\b(?:episodes?|ep)\b[-_.\s]*([^\n]+)$', stem, re.IGNORECASE)
    if m:
        raw_label = m.group(1).strip()
    else:
        m2 = re.search(r'(?:^|[-_.\s])(ova(?:\s*\d+)?|movie(?:\s*\d+)?|\d+(?:\.\d+)?(?:\[\d+\])?)\s*$', stem, re.IGNORECASE)
        raw_label = m2.group(1).strip() if m2 else stem

    from ..domain.episodes import clean_episode_identifier, parse_episode_dual_numbers
    prim, sec = parse_episode_dual_numbers(raw_label)
    clean_id = prim or clean_episode_identifier(raw_label) or raw_label

    try:
        prim_num = float(clean_id)
    except (ValueError, TypeError):
        prim_num = 999999.0

    try:
        sec_num = float(sec) if sec else 0.0
    except (ValueError, TypeError):
        sec_num = 0.0

    return prim_num, sec_num, clean_id, raw_label


def offline_file_sort_key(filepath: str) -> tuple[float, float, str]:
    prim_num, sec_num, _, _ = extract_offline_episode_info(filepath)
    return (prim_num, sec_num, os.path.basename(filepath))


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
            actual_files = [
                os.path.join(folder_path, f)
                for f in os.listdir(folder_path)
                if f.lower().endswith(VIDEO_EXTS)
            ]
            actual_files.sort(key=offline_file_sort_key)
        except OSError:
            actual_files = []

        discovered_eps = []
        for f in actual_files:
            _, _, clean_id, _ = extract_offline_episode_info(f)
            if clean_id and clean_id not in discovered_eps:
                discovered_eps.append(clean_id)

        valid_eps = discovered_eps

        if len(valid_eps) != len(data.get("episodes", [])):
            data["episodes"] = valid_eps
            dirty = True

        meta = data.get("metadata", {})
        if "originalEpisodeCount" not in meta and "episodeCount" in meta:
            meta["originalEpisodeCount"] = meta["episodeCount"]
        if not meta.get("episodeCount") and not meta.get("availableEpisodes"):
            meta["episodeCount"] = len(valid_eps)
            data["metadata"] = meta
            dirty = True
        meta["downloadedCount"] = len(valid_eps)

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
    if os.path.isdir(download_dir):
        for folder_name in os.listdir(download_dir):
            folder_path = os.path.join(download_dir, folder_name)
            if not os.path.isdir(folder_path) or folder_name in shows:
                continue
            try:
                files = [
                    os.path.join(folder_path, f)
                    for f in os.listdir(folder_path)
                    if f.lower().endswith(VIDEO_EXTS)
                ]
                files.sort(key=offline_file_sort_key)
            except OSError:
                continue
            if not files:
                continue
            episodes = []
            for f in files:
                _, _, clean_id, _ = extract_offline_episode_info(f)
                if clean_id and clean_id not in episodes:
                    episodes.append(clean_id)

            # Try to fetch real metadata for the discovered folder
            metadata = {"name": folder_name, "episodeCount": len(episodes)}

            data = {"metadata": metadata, "episodes": episodes}
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

        online_badge = "" if app_core.is_online() else "\033[38;2;225;85;85m[Offline]\033[0m │ "
        line = f"{online_badge}Downloaded anime  │  {download_dir}  │  Enter=episodes  Del=delete title  Esc=quit"
        if 0 <= si < len(valid_titles):
            title, data = valid_titles[si]
            show = data.get("metadata", {})
            parts.append(_poster_footer_line(show, line, w))
        else:
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
        delete_prompt="Delete this downloaded title? y/N",
        info_fn=make_info_fn(lambda: [d.get("metadata", {}) for _, d in valid_titles], ui),
        help_dict=picker_help("Open details", "Quit", "Quit", delete_label="Delete title")
    )
    if folder_idx < 0:
        return "QUIT"

    title, data = valid_titles[folder_idx]
    folder_path = os.path.join(download_dir, title)
    try:
        raw_files = os.listdir(folder_path)
        files = [os.path.join(folder_path, f) for f in raw_files if f.lower().endswith(VIDEO_EXTS)]
        files.sort(key=offline_file_sort_key)
    except OSError:
        files = []

    if not files:
        warn(f"No downloaded videos found in {title}.")
        return "DOWNLOADS"

    # Inject episodes into show metadata so the streaming UI can read them
    show = data.get("metadata", {})
    episodes_list = []
    if "_episode_labels" not in show or not isinstance(show.get("_episode_labels"), dict):
        show["_episode_labels"] = {}

    ms._download_files = {} # map ep_str -> filepath
    for filepath in files:
        _, _, clean_id, raw_label = extract_offline_episode_info(filepath)
        ep_str = clean_id
        episodes_list.append(ep_str)
        ms._download_files[ep_str] = filepath
        if raw_label:
            ms._download_files[raw_label] = filepath
            show["_episode_labels"][ep_str] = raw_label
            show["_episode_labels"][raw_label] = raw_label
        ms._download_files[os.path.basename(filepath)] = filepath

    show["_folder_name"] = title
    show["_downloaded_episodes"] = episodes_list

    # Check if catalog episode metadata exists in show or history
    catalog_eids = show.get("_episode_ids")
    if not catalog_eids:
        from allmanga_cli.core.storage import load_history
        from allmanga_cli.domain.matching import is_same_show
        for h in load_history():
            h_show = h.get("show") or {}
            if is_same_show(h_show, show):
                if h_show.get("_episode_ids"):
                    catalog_eids = list(h_show.get("_episode_ids"))
                    show["_episode_ids"] = catalog_eids
                    if h_show.get("_episode_labels"):
                        for k, v in h_show["_episode_labels"].items():
                            if k not in show["_episode_labels"]:
                                show["_episode_labels"][k] = v
                    if h_show.get("availableEpisodes"):
                        show["availableEpisodes"] = h_show["availableEpisodes"]
                    if h_show.get("episodeCount"):
                        show["episodeCount"] = h_show["episodeCount"]
                    if h_show.get("_id") and not show.get("_id"):
                        show["_id"] = h_show["_id"]
                    if h_show.get("_provider") and not show.get("_provider"):
                        show["_provider"] = h_show["_provider"]
                    if h_show.get("provider") and not show.get("provider"):
                        show["provider"] = h_show["provider"]
                    if h_show.get("_provider_name") and not show.get("_provider_name"):
                        show["_provider_name"] = h_show["_provider_name"]
                    if h_show.get("_provider_data") and not show.get("_provider_data"):
                        show["_provider_data"] = h_show["_provider_data"]
                break

    if catalog_eids:
        show["_episode_ids"] = catalog_eids
        show["_episode_ids_ttype"] = ttype
        show["_episode_catalog_state"] = "loaded"
        from allmanga_cli.domain.episodes import clean_episode_identifier, parse_episode_dual_numbers
        for eid in catalog_eids:
            lbl = show["_episode_labels"].get(eid, show["_episode_labels"].get(str(eid)))
            if lbl:
                prim, sec = parse_episode_dual_numbers(str(lbl))
                clean = (prim or clean_episode_identifier(str(lbl)) or str(lbl)).lstrip("0") or "0"
                for ep_key, fp in list(ms._download_files.items()):
                    f_prim, f_sec = parse_episode_dual_numbers(str(ep_key))
                    f_clean = (f_prim or clean_episode_identifier(str(ep_key)) or str(ep_key)).lstrip("0") or "0"
                    if f_clean == clean or (sec and sec == f_sec) or ep_key == lbl:
                        ms._download_files[eid] = fp
                        ms._download_files[str(eid)] = fp
                        break
    else:
        if "availableEpisodesDetail" not in show:
            show["availableEpisodesDetail"] = {}
        show["availableEpisodesDetail"][ttype] = episodes_list
        show["availableEpisodes"] = {ttype: len(episodes_list)}
        if "originalEpisodeCount" not in show and "episodeCount" in show:
            show["originalEpisodeCount"] = show["episodeCount"]
        show["episodeCount"] = len(episodes_list)
        show["_episode_ids"] = episodes_list
        show["_episode_ids_ttype"] = ttype
        show["_episode_catalog_state"] = "loaded"

    # Setup state machine variables for the selected offline anime
    ms._is_downloads = True
    ms._download_dir = folder_path
    ms.show_title = title
    ms.show_id = show.get("_id")
    ms.auto_download_next = cfg.get("auto_download_next", False)
    ms.auto_delete_watched = cfg.get("auto_delete_watched", False)
    ms.auto_delete_buffer = int(cfg.get("auto_delete_buffer", 1))
    set_ui_context(ui, show, ttype)
    ui.search_prev_state = "DOWNLOADS"
    ui.action_prev_state = "DOWNLOADS"
    ui.ep_prev_state = "DETAILS"

    return "DETAILS"
