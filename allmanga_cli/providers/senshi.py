import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Any
import logging

from .shared.base import Provider
from .shared.models import normalize_title, normalize_episode_catalog, normalize_episode_sources

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:146.0) Gecko/20100101 Firefox/146.0",
}

class Senshi(Provider):
    id = "senshi"

    def __init__(self, request_json_fn=None, *args, **kwargs):
        self._request_json = request_json_fn
        if not hasattr(self, 'metadata'):
            self.metadata = {}
        if not hasattr(self, 'domains'):
            self.domains = []

    @property
    def base_url(self) -> str:
        return self.domains[0] if getattr(self, 'domains', None) else "https://senshi.live"

    @property
    def name(self) -> str:
        return self.metadata.get("name", "Senshi")

    def _fetch_json(self, url: str) -> Any:
        headers = dict(HEADERS)
        headers["Referer"] = f"{self.base_url}/"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            logging.debug("Senshi HTTP error: %s", e)
            return []
        except Exception as e:
            logging.debug("Senshi fetch error: %s", e)
            return []

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
        from ..core.anilist_fallback import search_anilist_with_fallback
        data = search_anilist_with_fallback(query, graphql_query, {"search": query})

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
        episodes_data = self._fetch_json(f"{self.base_url}/episodes/{provider_id}")
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
        embeds = self._fetch_json(f"{self.base_url}/episode-embeds/{provider_id}/{episode}")
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
                "headers": {"Referer": f"{self.base_url}/"}
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
                "headers": {"Referer": f"{self.base_url}/"}
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
                "headers": {"Referer": f"{self.base_url}/"}
            })

        return normalize_episode_sources({
            "episode": {
                "sourceUrls": all_sources
            }
        }, provider_id=self.id, provider_title_id=provider_id, episode=episode)

    def browser_url(self, *, provider_id: str = "", episode: str = "") -> str:
        return self.base_url

PROVIDER_CLASS = Senshi
