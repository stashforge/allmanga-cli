import json
import os
import re

db_path = os.path.expanduser('~/.local/state/allmanga-cli/downloads_db.json')
with open(db_path, 'r') as f:
    db = json.load(f)

download_dir = db.get("current_download_dir", "")
if not download_dir:
    download_dir = os.path.expanduser("~/Videos/collection/allmanga-cli")

EP_NUM_RE = re.compile(r"Episode\s+(\d+(?:\.\d+)?)", re.IGNORECASE)

for title, show_data in list(db.get("shows", {}).items()):
    metadata = show_data.get("metadata", {})
    
    # Strip bloat
    keys_to_remove = ["_poster_raw", "availableEpisodesDetail", "_episode_ids", "_episode_ids_ttype", "_episode_catalog_state"]
    for k in keys_to_remove:
        metadata.pop(k, None)
        
    # Store originalEpisodeCount
    if "originalEpisodeCount" not in metadata and "episodeCount" in metadata:
        metadata["originalEpisodeCount"] = metadata["episodeCount"]
        
    # Resync episodes
    folder_path = os.path.join(download_dir, title)
    discovered_eps = set()
    if os.path.isdir(folder_path):
        for f in os.listdir(folder_path):
            m = EP_NUM_RE.search(f)
            if m:
                discovered_eps.add(m.group(1))
    
    def safe_float(x):
        try: return float(x)
        except ValueError: return 0
        
    show_data["episodes"] = sorted(list(discovered_eps), key=safe_float)

with open(db_path, 'w') as f:
    json.dump(db, f, indent=2)

print("Cleanup complete!")
