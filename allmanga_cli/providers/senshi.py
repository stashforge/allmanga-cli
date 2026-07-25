import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Any
import logging

from .shared.base import Provider
from .shared.models import normalize_title, normalize_episode_catalog, normalize_episode_sources

BASE_URL = "https://senshi.live"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
    "Referer": f"{BASE_URL}/"
}

class Senshi(Provider):
    id = "senshi"
    name = "Senshi"

    def __init__(self, *args, **kwargs):
        pass

    def _fetch_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise

    def search(self, query: str, ttype: str = "sub") -> list[dict[str, Any]]:
        # AniList GraphQL query to search and retrieve idMal
        graphql_query = """
        query($search: String) {
          Page(page: 1, perPage: 20) {
            media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
              id
              idMal
              title { romaji english native }
              format
              status
            }
          }
        }
        """
        req_data = json.dumps({
            "query": graphql_query,
            "variables": {"search": query}
        }).encode('utf-8')

        req = urllib.request.Request(
            "https://graphql.anilist.co",
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": HEADERS["User-Agent"]
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logging.getLogger(__name__).debug(f"Senshi search failed: {e}")
            return []

        media_list = data.get("data", {}).get("Page", {}).get("media", [])
        
        results = []
        for media in media_list:
            mal_id = media.get("idMal")
            if not mal_id:
                continue
                
            title_obj = media.get("title", {})
            title_str = title_obj.get("english") or title_obj.get("romaji") or title_obj.get("native") or "Unknown"
            
            results.append(normalize_title(
                {
                    "_id": str(mal_id),
                    "malId": mal_id,
                    "aniListId": media.get("id"),
                    "name": title_str,
                    "type": "anime",
                    "format": media.get("format"),
                    "status": media.get("status")
                },
                provider_id=self.id,
                provider_name=self.name
            ))
            
        return results

    def get_title(self, provider_id: str) -> dict[str, Any]:
        return {
            "name": f"MAL ID: {provider_id}",
            "url": f"https://myanimelist.net/anime/{provider_id}",
        }

    def episode_catalog(self, provider_id: str, ttype: str = "sub") -> dict[str, Any]:
        episodes_data = self._fetch_json(f"{BASE_URL}/episodes/{provider_id}")
        if not episodes_data:
            return normalize_episode_catalog(
                {"episodes": []},
                provider_id=self.id,
                provider_title_id=provider_id,
            )

        # episodes_data is a list of {"ep_id": 1, "ep_title": "...", ...}
        eps_formatted = []
        ids = []
        labels = {}

        for ep in episodes_data:
            ep_num = str(ep.get("ep_id"))
            
            ids.append(ep_num)
            labels[ep_num] = ep_num
            eps_formatted.append({
                "id": ep_num,
                "label": ep_num
            })
            
        def _parse_ep(val):
            try: return float(val)
            except ValueError: return 0.0

        # sort by number
        eps_formatted.sort(key=lambda x: _parse_ep(x["id"]))
        ids = [ep["id"] for ep in eps_formatted]

        return normalize_episode_catalog(
            {
                "state": "loaded",
                "ids": ids,
                "labels": labels,
                "episodes": {ttype: eps_formatted}
            },
            provider_id=self.id,
            provider_title_id=provider_id,
        )

    def episode_sources(self, provider_id: str, episode: str, ttype: str = "sub") -> dict[str, Any] | None:
        embeds = self._fetch_json(f"{BASE_URL}/episode-embeds/{provider_id}/{episode}")
        if not embeds:
            return None

        want_dub = (ttype.lower() == "dub")
        
        # Filter by status (HardSub vs Dub)
        def is_dub(status):
            return str(status).lower() == "dub"

        # Try to find a matching source
        source = None
        for emb in embeds:
            if is_dub(emb.get("status")) == want_dub:
                source = emb
                break

        # Fallback if preferred audio not found
        if not source and embeds:
            source = embeds[0]

        if not source:
            return None

        all_sources = []

        # 1. Direct Senshi M3U8 (Highest Priority)
        senshi_url = source.get("url")
        if senshi_url:
            all_sources.append({
                "sourceName": "Senshi",
                "link": senshi_url,
                "resolution": "auto",
                "type": "hls",
                "priority": 5,
                "headers": {"Referer": f"{BASE_URL}/"}
            })

        # 2. Server 2 (StreamNin)
        server2 = source.get("server2")
        if server2:
            all_sources.append({
                "sourceName": "StreamNin (Embed)",
                "link": server2,
                "resolution": "auto",
                "type": "embed",
                "priority": 3,
                "headers": {"Referer": f"{BASE_URL}/"}
            })

        # 3. Server FM (FileMoon)
        serverFM = source.get("serverFM")
        if serverFM:
            all_sources.append({
                "sourceName": "FileMoon (Embed)",
                "link": serverFM,
                "resolution": "auto",
                "type": "embed",
                "priority": 2,
                "headers": {"Referer": f"{BASE_URL}/"}
            })

        return normalize_episode_sources({
            "episode": {
                "sourceUrls": all_sources
            }
        }, provider_id=self.id, provider_title_id=provider_id, episode=episode)

    def browser_url(self, *, provider_id: str = "", episode: str = "") -> str:
        return BASE_URL

PROVIDER_CLASS = Senshi
