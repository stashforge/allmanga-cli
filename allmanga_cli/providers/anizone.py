"""AniZone provider adapter."""

from __future__ import annotations

import logging
import urllib.request
import urllib.parse
from typing import Any
from bs4 import BeautifulSoup

_logger = logging.getLogger(__name__)

from .models import (
    normalize_episode_catalog,
    normalize_episode_sources,
    normalize_title,
    normalize_titles,
)

class AniZoneProvider:
    id = "anizone"
    name = "AniZone"

    def __init__(self, request_json_fn=None):
        self._request_json = request_json_fn
        self.base_url = "https://anizone.to"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        }

    def search(self, query: str, ttype: str = "sub") -> list[dict[str, Any]]:
        import re
        search_url = f"{self.base_url}/anime?search={urllib.parse.quote(query)}"
        req = urllib.request.Request(search_url, headers=self.headers)
        try:
            html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            seen_ids = set()
            
            for container in soup.find_all(['div', 'li'], attrs={'x-data': True}):
                x_data = container.get('x-data', '')
                if 'anmTitles' in x_data and 'window.getTitle' in x_data:
                    # Extract title fallback
                    m_title = re.search(r"window\.getTitle\([^,]+,\s*'((?:[^'\\]|\\.)*)'\)", x_data)
                    title = m_title.group(1) if m_title else None
                    
                    if title:
                        title = title.replace("\\'", "'").replace('\\"', '"')
                        # Find the a tag inside
                        a = container.find('a', href=lambda h: h and h.startswith(f"{self.base_url}/anime/"))
                        if a:
                            anime_id = a['href'].split('/')[-1]
                            if anime_id not in seen_ids:
                                anime_info = {
                                    "_id": anime_id,
                                    "name": title
                                }
                                
                                # Extract Thumbnail
                                img = container.find('img')
                                if img and img.get('src'):
                                    anime_info['thumbnail'] = img['src']
                                
                                # Extract Metadata (Format, Year, Eps, Status)
                                # Spans could use not-last:after:mx-1 or not-first:before:mx-1
                                meta_spans = container.find_all('span', class_=lambda c: c and ('not-last:after:mx-1' in c or 'not-first:before:mx-1' in c))
                                if meta_spans:
                                    texts = [s.text.strip() for s in meta_spans if s.text.strip()]
                                    if len(texts) > 0:
                                        anime_info['format'] = texts[0]
                                    if len(texts) > 1:
                                        try:
                                            anime_info['airedStart'] = {"year": int(texts[1])}
                                        except ValueError:
                                            pass
                                    for t in texts:
                                        if 'Eps' in t or 'Ep' in t:
                                            anime_info['episodeCount'] = t.split()[0]
                                        elif t.lower() in ['completed', 'releasing', 'on hiatus', 'cancelled']:
                                            anime_info['status'] = t
                                
                                # Extract Genres
                                genre_div = container.find('div', class_=lambda c: c and 'flex-wrap' in c)
                                if genre_div:
                                    genre_links = genre_div.find_all('a')
                                    genres = [g.text.strip() for g in genre_links if g.text.strip()]
                                    if genres:
                                        anime_info['genres'] = genres
                                        
                                results.append(anime_info)
                                seen_ids.add(anime_id)
            
            return normalize_titles(results, provider_id=self.id, provider_name=self.name)
        except Exception as e:
            _logger.debug("AniZone search error: %s", e)
            return []

    def get_title(self, provider_id: str) -> dict[str, Any] | None:
        # Simplest implementation, we don't have full details easily
        return normalize_title({"_id": provider_id, "name": provider_id}, provider_id=self.id, provider_name=self.name)

    def episode_catalog(self, provider_id: str, ttype: str = "sub") -> dict[str, Any]:
        anime_url = f"{self.base_url}/anime/{provider_id}"
        req = urllib.request.Request(anime_url, headers=self.headers)
        try:
            html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            ids = []
            seen_ids = set()
            for a in soup.find_all('a'):
                href = a.get('href', '')
                if href.startswith(f"{anime_url}/"):
                    ep_part = href.split('/')[-1]
                    if ep_part.isdigit() and ep_part not in seen_ids:
                        ids.append(ep_part)
                        seen_ids.add(ep_part)
            ids.sort(key=lambda x: int(x))
            return normalize_episode_catalog({"ids": ids}, provider_id=self.id, provider_title_id=provider_id)
        except Exception as e:
            _logger.debug("AniZone episode catalog error: %s", e)
            return normalize_episode_catalog({"ids": []}, provider_id=self.id, provider_title_id=provider_id)

    def episode_sources(
        self,
        provider_id: str,
        episode: str,
        ttype: str = "sub",
    ) -> dict[str, Any] | None:
        ep_url = f"{self.base_url}/anime/{provider_id}/{episode}"
        req = urllib.request.Request(ep_url, headers=self.headers)
        try:
            html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            
            source_urls = []
            media_player = soup.find('media-player')
            if media_player and media_player.get('src'):
                stream_url = media_player.get('src')

                source_urls.append({
                    "sourceName": "AniZone",
                    "streamUrl": stream_url,
                    "type": "hls",
                    "priority": 1,
                    "resolution": "auto"
                })
            
            return normalize_episode_sources(
                {"episode": {"sourceUrls": source_urls}},
                provider_id=self.id,
                provider_title_id=provider_id,
                episode=episode,
            )
        except Exception as e:
            _logger.debug("AniZone sources error: %s", e)
            return None

    def browser_url(
        self,
        provider_id: str,
        episode: str | None = None,
        ttype: str = "sub",
        cfg: dict[str, Any] | None = None,
    ) -> str:
        if not episode:
            return f"{self.base_url}/anime/{provider_id}"
        return f"{self.base_url}/anime/{provider_id}/{episode}"

PROVIDER_CLASS = AniZoneProvider

