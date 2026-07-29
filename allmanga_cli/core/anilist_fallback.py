import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import logging

ANILIST_URL = "https://graphql.anilist.co"

def _extract_ani_id(data) -> int | None:
    if isinstance(data, dict):
        if "aniId" in data and isinstance(data["aniId"], int):
            return data["aniId"]
        for key, value in data.items():
            res = _extract_ani_id(value)
            if res is not None:
                return res
    elif isinstance(data, list):
        for item in data:
            res = _extract_ani_id(item)
            if res is not None:
                return res
    return None

def _fetch_jikan_fallback(query: str) -> tuple[bool, dict]:
    logging.getLogger(__name__).debug("Using Jikan fallback for search")
    jikan_url = f"https://api.tenrai.org/v1/anime?q={urllib.parse.quote(query)}&sfw=true&limit=10"
    req = urllib.request.Request(jikan_url, headers={"User-Agent": "allmanga-cli"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            jikan_data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logging.getLogger(__name__).debug(f"Jikan fallback failed: {e}")
        return False, {"data": {"Page": {"media": []}}}
    
    media_list = []
    for item in jikan_data.get("data", []):
        mal_id = item.get("mal_id")
        if not mal_id:
            continue
            
        ani_id = mal_id  # Fallback to mal_id if malsync fails
        try:
            ms_req = urllib.request.Request(
                f"https://api.malsync.moe/mal/anime/{mal_id}",
                headers={"User-Agent": "allmanga-cli"}
            )
            with urllib.request.urlopen(ms_req, timeout=5) as m_res:
                ms_data = json.loads(m_res.read().decode('utf-8'))
                found_ani_id = _extract_ani_id(ms_data)
                if found_ani_id:
                    ani_id = found_ani_id
        except Exception:
            pass

        title_dict = {
            "english": item.get("title_english"),
            "romaji": item.get("title"),
            "native": item.get("title_japanese")
        }
        
        # Approximate AniList format
        format_mapping = {
            "TV": "TV",
            "Movie": "MOVIE",
            "OVA": "OVA",
            "ONA": "ONA",
            "Special": "SPECIAL",
            "Music": "MUSIC"
        }
        fmt = format_mapping.get(item.get("type"), "TV")
        
        status_mapping = {
            "Finished Airing": "FINISHED",
            "Currently Airing": "RELEASING",
            "Not yet aired": "NOT_YET_RELEASED"
        }
        status = status_mapping.get(item.get("status"), "FINISHED")
        
        season = item.get("season")
        if season:
            season = season.upper()
            
        genres = [g.get("name") for g in item.get("genres", [])]

        media_list.append({
            "id": ani_id,
            "idMal": mal_id,
            "title": title_dict,
            "description": item.get("synopsis"),
            "coverImage": {"large": item.get("images", {}).get("jpg", {}).get("large_image_url")},
            "bannerImage": None,
            "format": fmt,
            "status": status,
            "season": season,
            "seasonYear": item.get("year"),
            "episodes": item.get("episodes"),
            "averageScore": int(item.get("score", 0) * 10) if item.get("score") else None,
            "genres": genres
        })
        
    return True, {"data": {"Page": {"media": media_list}}}

def search_anilist_with_fallback(query: str, raw_gql_query: str, variables: dict) -> dict:
    req_data = json.dumps({
        "query": raw_gql_query,
        "variables": variables
    }).encode('utf-8')
    
    req = urllib.request.Request(
        ANILIST_URL,
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "allmanga-cli"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError) as e:
        # Check if it's a network error or 5xx/429
        should_fallback = False
        if isinstance(e, urllib.error.HTTPError):
            if e.code >= 500 or e.code == 429:
                should_fallback = True
        else:
            # URLError like timeout or connection refused
            should_fallback = True
            
        if should_fallback:
            logging.getLogger(__name__).debug("AniList search failed, using Jikan fallback.")
            success, fallback_data = _fetch_jikan_fallback(query)
            if not success:
                from .api import SearchFailure
                raise SearchFailure("API Error: Both AniList and Jikan are currently down or rate-limited.")
            return fallback_data
        
        return {"data": {"Page": {"media": []}}}
