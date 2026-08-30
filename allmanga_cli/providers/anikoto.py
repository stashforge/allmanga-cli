import logging
import urllib.request
import urllib.parse
import json
import re
from typing import Any

from .shared.models import (
    normalize_episode_catalog,
    normalize_episode_sources,
    normalize_title,
    normalize_titles,
)
from allmanga_cli.services import anilist
from allmanga_cli.services import normalize as anilist_normalize

_logger = logging.getLogger(__name__)

class AnikotoProvider:
    id = "anikoto"
    audio_mode = "separate_catalogs"

    def __init__(self, request_json_fn=None):
        self._request_json = request_json_fn
        if not hasattr(self, 'metadata'):
            self.metadata = {}
        if not hasattr(self, 'domains'):
            self.domains = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        }

    @property
    def base_url(self) -> str:
        return self.domains[0] if getattr(self, 'domains', None) else "https://megaplay.buzz"

    @property
    def name(self) -> str:
        return self.metadata.get("name", "Anikoto")

    def search(self, query: str, ttype: str = "sub") -> list[dict[str, Any]]:
        try:
            raw_results = anilist.fetch(urllib.request.urlopen, json.load, None, search=query)
            results = []
            for raw in raw_results:
                m = anilist_normalize.normalize_media(raw)
                if m:
                    eps = m.get("availableEpisodes", {})
                    eps["dub"] = eps.get("sub", 0)
                    results.append(m)
            return normalize_titles(results, provider_id=self.id, provider_name=self.name, id_key="_id")
        except Exception as e:
            _logger.debug("Anikoto search error: %s", e)
            return []

    def get_title(self, provider_id: str) -> dict[str, Any] | None:
        try:
            media = anilist.fetch_one(urllib.request.urlopen, json.load, None, anilist_id=provider_id)
            if not media:
                return None
            title_data = anilist_normalize.normalize_media(media)
            if title_data:
                eps = title_data.get("availableEpisodes", {})
                eps["dub"] = eps.get("sub", 0)
            return normalize_title(title_data, provider_id=self.id, provider_name=self.name, id_key="_id")
        except Exception as e:
            _logger.debug("Anikoto get_title error: %s", e)
            return None

    def episode_catalog(self, provider_id: str, ttype: str = "sub") -> dict[str, Any]:
        try:
            media = anilist.fetch_one(urllib.request.urlopen, json.load, None, anilist_id=provider_id)
            if not media:
                return normalize_episode_catalog({"ids": []}, provider_id=self.id, provider_title_id=provider_id)
                
            total = media.get("episodes")
            if not total:
                next_airing = media.get("nextAiringEpisode")
                if next_airing and next_airing.get("episode"):
                    total = next_airing["episode"] - 1
                else:
                    total = 1  # Fallback
                    
            ids = [str(ep) for ep in range(1, total + 1)]
            
            # If in DUB mode, check if MegaPlay actually has dub for episode 1
            if ttype == "dub":
                probe_url = f"{self.base_url}/stream/ani/{provider_id}/1/dub"
                req = urllib.request.Request(
                    probe_url,
                    headers={
                        **self.headers,
                        "Referer": f"{self.base_url}/",
                        "Accept": "text/html,application/json,*/*",
                    },
                )
                has_dub = False
                try:
                    html = urllib.request.urlopen(req, timeout=4).read().decode("utf-8", errors="ignore")
                    has_dub = bool(re.search(r'data-id=["\'](\d+)["\']', html))
                except Exception:
                    pass
                if not has_dub:
                    return normalize_episode_catalog({
                        "ids": [],
                        "state": "loaded",
                        "error": "No English DUB available for this anime on Anikoto.",
                        "detail": {"sub": ids, "dub": [], "raw": []},
                    }, provider_id=self.id, provider_title_id=provider_id)

            detail = {
                "sub": ids,
                "dub": ids if ttype == "dub" else [],
                "raw": [],
            }
            return normalize_episode_catalog({"ids": ids, "detail": detail}, provider_id=self.id, provider_title_id=provider_id)
        except Exception as e:
            _logger.debug("Anikoto episode_catalog error: %s", e)
            return normalize_episode_catalog({"ids": []}, provider_id=self.id, provider_title_id=provider_id)

    def episode_sources(
        self,
        provider_id: str,
        episode: str,
        ttype: str = "sub",
    ) -> dict[str, Any] | None:
        
        # 1. Fetch Embed
        embed_url = f"{self.base_url}/stream/ani/{provider_id}/{episode}/{ttype}"
        req_embed = urllib.request.Request(
            embed_url,
            headers={
                **self.headers,
                "Referer": f"{self.base_url}/",
                "Accept": "text/html,application/json,text/plain,*/*"
            }
        )
        try:
            html = urllib.request.urlopen(req_embed, timeout=7).read().decode('utf-8', errors='ignore')
            match = re.search(r'data-id=["\'](\d+)["\']', html)
            if not match:
                return None
            data_id = match.group(1)
            
            # 2. Fetch getSources API
            api_url = f"{self.base_url}/stream/getSources?id={data_id}"
            req_api = urllib.request.Request(
                api_url,
                headers={
                    **self.headers,
                    "Referer": embed_url,
                    "Origin": self.base_url,
                    "Accept": "application/json,text/plain,*/*"
                }
            )
            res_api = urllib.request.urlopen(req_api, timeout=7).read().decode('utf-8')
            sources_data = json.loads(res_api)
            
            source_urls = []
            raw_sources = sources_data.get("sources", [])
            if isinstance(raw_sources, dict):
                raw_sources = [raw_sources]
                
            for source in raw_sources:
                url = source.get("file") or source.get("url")
                if not url:
                    continue
                
                # Fetch and parse the m3u8 manually to get different qualities
                if url.endswith(".m3u8"):
                    # Add original master URL as Auto quality
                    source_urls.append({
                        "sourceName": "MegaPlay (Auto)",
                        "streamUrl": url,
                        "type": "hls",
                        "priority": 1,
                        "resolution": "auto",
                        "headers": {
                            "Referer": f"{self.base_url}/",
                            "Origin": self.base_url,
                            "User-Agent": self.headers["User-Agent"]
                        }
                    })
                    
                    try:
                        req_m3u8 = urllib.request.Request(
                            url,
                            headers={
                                **self.headers,
                                "Referer": f"{self.base_url}/",
                                "Origin": self.base_url,
                            }
                        )
                        m3u8_text = urllib.request.urlopen(req_m3u8, timeout=7).read().decode('utf-8')
                        
                        # Only parse if it's a master playlist containing variants
                        if "#EXT-X-STREAM-INF" in m3u8_text:
                            lines = m3u8_text.splitlines()
                            variants = []
                            for i, line in enumerate(lines):
                                if line.startswith("#EXT-X-STREAM-INF"):
                                    res_match = re.search(r'RESOLUTION=\d+x(\d+)', line)
                                    res_int = int(res_match.group(1)) if res_match else 0
                                    quality = f"{res_int}p" if res_int else "auto"
                                    
                                    if i + 1 < len(lines):
                                        uri = lines[i+1].strip()
                                        if uri and not uri.startswith("#"):
                                            variant_url = urllib.parse.urljoin(url, uri)
                                            variants.append({
                                                "sourceName": f"MegaPlay ({quality})",
                                                "streamUrl": variant_url,
                                                "type": "hls",
                                                "priority": 1,
                                                "resolution": str(res_int) if res_int else 'auto',
                                                "sort_key": res_int,
                                                "headers": {
                                                    "Referer": f"{self.base_url}/",
                                                    "Origin": self.base_url,
                                                    "User-Agent": self.headers["User-Agent"]
                                                }
                                            })
                            
                            if variants:
                                # Sort descending by resolution (e.g. 1080 -> 720 -> 360)
                                variants.sort(key=lambda x: x["sort_key"], reverse=True)
                                # Clean up sort_key before appending
                                for v in variants:
                                    del v["sort_key"]
                                    source_urls.append(v)
                                continue # Skip the default fallback append if we successfully parsed variants
                    except Exception as parse_e:
                        _logger.debug("Failed to parse m3u8 qualities manually: %s", parse_e)
                
                # Fallback: Just append the original URL if not m3u8 or parsing failed
                source_urls.append({
                    "sourceName": "MegaPlay",
                    "streamUrl": url,
                    "type": "hls" if url.endswith(".m3u8") else "mp4",
                    "priority": 1,
                    "resolution": "auto",
                    "headers": {
                        "Referer": f"{self.base_url}/",
                        "Origin": self.base_url,
                        "User-Agent": self.headers["User-Agent"]
                    }
                })
                
            return normalize_episode_sources(
                {"episode": {"sourceUrls": source_urls}},
                provider_id=self.id,
                provider_title_id=provider_id,
                episode=episode,
            )
            
        except Exception as e:
            _logger.debug("Anikoto sources error: %s", e)
            return None

    def browser_url(
        self,
        provider_id: str,
        episode: str | None = None,
        ttype: str = "sub",
        cfg: dict[str, Any] | None = None,
    ) -> str:
        if episode:
            return f"{self.base_url}/stream/ani/{provider_id}/{episode}/{ttype}"
        return f"https://anilist.co/anime/{provider_id}"

PROVIDER_CLASS = AnikotoProvider
