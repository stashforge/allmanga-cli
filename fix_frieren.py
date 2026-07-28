import json
import os
from allmanga_cli.app_core import fetch_anilist_media, load_config
from allmanga_cli.core.storage import load_downloads_db, save_downloads_db

cfg = load_config()
db = load_downloads_db()

title = "Frieren Beyond Journeys End"
show_data = db.get("shows", {}).get(title)
if not show_data:
    print("Show not found")
    exit(1)

metadata = show_data.get("metadata", {})
anilist_id = metadata.get("aniListId") or "154587"

token = cfg.get("anilist_token")
media = fetch_anilist_media(token, anilist_id)

if media:
    # Update essential fields
    metadata["episodeCount"] = media.get("episodes")
    metadata["originalEpisodeCount"] = media.get("episodes")
    metadata["name"] = media.get("title", {}).get("romaji") or metadata.get("name")
    metadata["englishName"] = media.get("title", {}).get("english") or metadata.get("englishName")
    metadata["status"] = media.get("status") or metadata.get("status")
    metadata["description"] = media.get("description") or metadata.get("description")
    
    # Optional mapping
    from allmanga_cli.app_core import update_anime_from_anilist_media
    # update_anime_from_anilist_media modifies the dictionary in place
    update_anime_from_anilist_media(metadata, media)
    
    # Strip any potential bloat added by update_anime_from_anilist_media just in case
    # using the offline metadata builder logic we defined earlier
    keys_to_keep = [
        "id", "name", "englishName", "nativeName", "altNames",
        "thumbnail", "banner", "description", "type", "format",
        "status", "season", "airedStart", "airedEnd", "startDate",
        "endDate", "score", "genres", "tags", "aniListId", "malId",
        "_display_name", "_display_english_name", "_anilist_list",
        "_anilist_progress", "_anilist_score", "anilistMatch",
        "originalEpisodeCount", "_id", "_provider", "_provider_id",
        "_provider_name", "_local_progress", "_local_episode_label"
    ]
    
    clean_metadata = {k: metadata[k] for k in keys_to_keep if k in metadata}
    db["shows"][title]["metadata"] = clean_metadata
    
    save_downloads_db(db)
    print("Updated Frieren metadata successfully.")
    print(f"Original Episode Count: {clean_metadata.get('originalEpisodeCount')}")
else:
    print("Failed to fetch media from AniList.")
