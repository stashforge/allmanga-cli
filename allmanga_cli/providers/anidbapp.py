import json
import re
import urllib.parse
import urllib.request
import urllib.error
from typing import Any
import logging

from .shared.base import Provider
from .shared.models import (
    normalize_title,
    normalize_titles,
    normalize_episode_catalog,
    normalize_episode_sources,
)

log = logging.getLogger(__name__)

# Base headers that mirror Chrome, needed to bypass Cloudflare
NAV_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
}

XHR_HEADERS = {
    "Accept": "application/json, text/html, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": "\"Google Chrome\";v=\"137\", \"Chromium\";v=\"137\", \"Not/A)Brand\";v=\"24\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
}

class AniDBApp(Provider):
    id = "anidbapp"

    def __init__(self, request_json_fn=None):
        self._request_json = request_json_fn
        if not hasattr(self, 'metadata'):
            self.metadata = {}
        if not hasattr(self, 'domains'):
            self.domains = []

    @property
    def base_url(self) -> str:
        return self.domains[0] if getattr(self, 'domains', None) else "https://anidb.app"

    @property
    def name(self) -> str:
        return self.metadata.get("name", "AniDB.app")

    def _fetch(self, url, headers):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")
        except Exception as e:
            return 500, str(e)

    def search(self, query: str, ttype: str = "sub") -> list[dict[str, Any]]:
        url = f"{self.base_url}/browse?q={urllib.parse.quote(query)}"
        headers = dict(NAV_HEADERS)
        headers["Referer"] = f"{self.base_url}/home"

        status, html = self._fetch(url, headers=headers)
        if status != 200:
            log.warning(f"AniDBApp search failed: HTTP {status}")
            return []
            
        results = []
        seen = set()
        
        # Parse the raw HTML for grid cards
        # <a href="https://anidb.app/anime/slug" class="anime-card..." title="Title">
        for match in re.finditer(r'<a\b[^>]*href=["\'](?:https://anidb\.app)?/anime/([^"\']+)["\'][^>]*class=["\'][^"\']*anime-card[^"\']*["\']([^>]*)>([\s\S]*?)</a>', html, re.IGNORECASE):
            slug = match.group(1)
            attrs = match.group(2)
            content = match.group(3)
            
            if slug in seen:
                continue
            seen.add(slug)
            
            title_match = re.search(r'title=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).replace("&amp;", "&").replace("&#039;", "'")
            else:
                title_match2 = re.search(r'<p\b[^>]*class=["\'][^"\']*font-semibold[^"\']*["\'][^>]*>([\s\S]*?)</p>', content, re.IGNORECASE)
                title = re.sub(r'<[^>]+>', '', title_match2.group(1)).strip() if title_match2 else slug.replace('-', ' ')
                title = title.replace("&#039;", "'")
            
            # Extract thumbnail
            thumbnail = ""
            img_tag_match = re.search(r'<img\b([^>]+)>', content, re.IGNORECASE)
            if img_tag_match:
                src_match = re.search(r'\bsrc=["\']([^"\']+)["\']', img_tag_match.group(1), re.IGNORECASE)
                if src_match:
                    thumbnail = src_match.group(1).replace("&amp;", "&")

            # Extract type if present (e.g., Movie, TV)
            show_type = "TV"
            type_match = re.search(r'<span\b[^>]*badge-orange[^>]*>([\s\S]*?)</span>', content, re.IGNORECASE)
            if type_match:
                show_type = re.sub(r'<[^>]+>', '', type_match.group(1)).strip()
            
            results.append({
                "id": slug,
                "name": title,
                "type": show_type,
                "thumbnail": thumbnail,
                "startDate": None,
            })
            
        return normalize_titles(results, provider_id=self.id, provider_name=self.name, id_key="id")

    def get_title(self, provider_id: str) -> dict[str, Any] | None:
        # provider_id is the slug, e.g., one-piece-0948
        url = f"{self.base_url}/anime/{provider_id}"
        headers = dict(NAV_HEADERS)
        headers["Referer"] = f"{self.base_url}/home"
        
        status, text = self._fetch(url, headers=headers)
        if status != 200:
            return None
            
        title_match = re.search(r'<h1\b[^>]*>([\s\S]*?)</h1>', text, re.IGNORECASE)
        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else provider_id.replace('-', ' ')
        
        anilist_match = re.search(r'href=["\']https?://anilist\.co/anime/(\d+)["\']', text, re.IGNORECASE)
        mal_match = re.search(r'href=["\']https?://myanimelist\.net/anime/(\d+)["\']', text, re.IGNORECASE)
        
        result = {
            "id": provider_id,
            "name": title,
        }
        if anilist_match:
            result["aniListId"] = int(anilist_match.group(1))
        if mal_match:
            result["malId"] = int(mal_match.group(1))
        
        return normalize_title(result, provider_id=self.id, provider_name=self.name, id_key="id")

    def episode_catalog(self, provider_id: str, ttype: str = "sub") -> dict[str, Any]:
        # Extract siteId from the slug
        m = re.search(r'-(\d+)$', provider_id)
        if not m:
            log.warning(f"Could not extract siteId from slug: {provider_id}")
            return normalize_episode_catalog({"state": "error", "error": "Invalid siteId"}, provider_id=self.id, provider_title_id=provider_id)
            
        site_id = m.group(1)
        url = f"{self.base_url}/api/frontend/anime/{site_id}/episodes"
        headers = dict(XHR_HEADERS)
        headers["Referer"] = f"{self.base_url}/anime/{provider_id}"
        
        status, text = self._fetch(url, headers=headers)
        if status != 200:
            log.warning(f"AniDBApp episode catalog failed: HTTP {status}")
            return normalize_episode_catalog({"state": "error", "error": "API failed"}, provider_id=self.id, provider_title_id=provider_id)
            
        try:
            data = json.loads(text)
        except Exception:
            log.error("Failed to parse AniDBApp episode catalog JSON")
            return normalize_episode_catalog({"state": "error", "error": "Invalid JSON"}, provider_id=self.id, provider_title_id=provider_id)
            
        episodes_list = data.get("episodes", [])
        episodes_map = {}
        ids = []
        eps_formatted = []
        labels = {}
        
        for ep in episodes_list:
            # We map string episode numbers to internal ids
            ep_num = str(ep.get("number"))
            if ep_num and ep_num not in episodes_map:
                episodes_map[ep_num] = ep.get("id")
                ids.append(ep_num)
                labels[ep_num] = f"Episode {ep_num}"
                eps_formatted.append({"id": ep_num, "label": labels[ep_num]})
                
        catalog = {
            "state": "loaded",
            "ids": ids,
            "labels": labels,
            "episodes": {ttype: eps_formatted},
            "_internal_map": episodes_map,
        }
            
        return normalize_episode_catalog(catalog, provider_id=self.id, provider_title_id=provider_id)

    def episode_sources(
        self,
        provider_id: str,
        episode: str,
        ttype: str = "sub",
    ) -> dict[str, Any] | None:
        
        # First, fetch the catalog to get the internal episode ID
        catalog = self.episode_catalog(provider_id, ttype)
        internal_map = catalog.get("_internal_map", {})
        ep_id = internal_map.get(str(episode))
        
        if not ep_id:
            log.warning(f"Episode {episode} not found in AniDBApp catalog for {provider_id}")
            return None
            
        # Fetch languages for the episode
        url = f"{self.base_url}/api/frontend/episode/{ep_id}/languages"
        headers = dict(XHR_HEADERS)
        headers["Referer"] = f"{self.base_url}/anime/{provider_id}"
        
        status, text = self._fetch(url, headers=headers)
        if status != 200:
            log.warning(f"AniDBApp episode languages failed: HTTP {status}")
            return None
            
        try:
            data = json.loads(text)
        except Exception:
            return None
            
        languages = data.get("languages", [])
        preferred = ["jpn", "ja", "japanese"] if ttype == "sub" else ["eng", "en", "english"]
        
        matched_lang = None
        for lang in languages:
            code = str(lang.get("code", "")).lower()
            name = str(lang.get("name", "")).lower()
            if code in preferred or name in preferred:
                matched_lang = lang
                break
                
        # Fallback to the first available if exact sub/dub doesn't match perfectly, 
        # though usually it's correct.
        if not matched_lang and languages:
            matched_lang = languages[0]
            
        if not matched_lang or not matched_lang.get("embed_url"):
            log.warning(f"No embed URL found for {ttype} in {languages}")
            return None
            
        embed_url = matched_lang["embed_url"]
        
        # Hit the embed URL to extract the HLS stream
        embed_headers = dict(NAV_HEADERS)
        embed_headers["Referer"] = f"{self.base_url}/"
        
        embed_status, html = self._fetch(embed_url, headers=embed_headers)
        if embed_status != 200:
            log.warning(f"AniDBApp embed fetch failed: HTTP {embed_status}")
            return None
            
        hls_url = None
        patterns = [
            r'file\s*:\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
            r'sources\s*:\s*\[\s*\{[^}]*file\s*:\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
            r'["\'](https?://[^"\']+/master\.m3u8[^"\']*)["\']',
            r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
        ]
        
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                hls_url = m.group(1).replace("&amp;", "&")
                break
                
        if not hls_url:
            log.warning(f"Could not extract HLS URL from embed: {embed_url}")
            return None
            
        stream_referer = f"{urllib.parse.urlparse(embed_url).scheme}://{urllib.parse.urlparse(embed_url).netloc}/"
        
        sourceUrls = [{
            "sourceName": "AniDB.app Direct",
            "priority": 0,
            "resolution": "auto",
            "type": "hls",
            "link": hls_url,
            "headers": {"Referer": stream_referer, "User-Agent": NAV_HEADERS["User-Agent"]},
        }]
        
        return normalize_episode_sources(
            {"episode": {"sourceUrls": sourceUrls}},
            provider_id=self.id,
            provider_title_id=provider_id,
            episode=episode,
        )

    def browser_url(
        self,
        provider_id: str,
        episode: str | None = None,
        ttype: str = "sub",
        cfg: dict[str, Any] | None = None,
    ) -> str:
        return f"{self.base_url}/anime/{provider_id}"

PROVIDER_CLASS = AniDBApp


