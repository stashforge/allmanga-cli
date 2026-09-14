import logging
import urllib.request
import urllib.parse
import json
import re
from typing import Any
from bs4 import BeautifulSoup

from .shared.models import (
    normalize_episode_catalog,
    normalize_episode_sources,
    normalize_title,
    normalize_titles,
)
from allmanga_cli.services import anilist
from allmanga_cli.services import normalize as anilist_normalize

_logger = logging.getLogger(__name__)

_MEGAPLAY_KEY = b"i?LMTAx0Q6,:}50U".ljust(32, b"\x00")
_MEGAPLAY_IV = b"W0;27ToaUpl_P%'c"


def _decrypt_megaplay_enc(enc: str) -> dict | None:
    if not enc:
        return None
    try:
        import base64
        enc_clean = enc.replace("-", "+").replace("_", "/")
        rem = len(enc_clean) % 4
        if rem:
            enc_clean += "=" * (4 - rem)
        ciphertext = base64.b64decode(enc_clean)

        plaintext = None
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            cipher = Cipher(algorithms.AES(_MEGAPLAY_KEY), modes.CBC(_MEGAPLAY_IV), backend=default_backend())
            decryptor = cipher.decryptor()
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        except Exception:
            for lib in ("Cryptodome", "Crypto"):
                try:
                    AES = __import__(f"{lib}.Cipher", fromlist=["AES"]).AES
                    cipher = AES.new(_MEGAPLAY_KEY, AES.MODE_CBC, _MEGAPLAY_IV)
                    plaintext = cipher.decrypt(ciphertext)
                    break
                except ImportError:
                    continue
                except Exception:
                    pass

        if not plaintext:
            return None

        pad_len = plaintext[-1]
        if 0 < pad_len <= 16:
            plaintext = plaintext[:-pad_len]
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        _logger.debug("Failed to decrypt MegaPlay enc: %s", e)
        return None


class AnikotoProvider:
    id = "anikoto"
    audio_mode = "separate_catalogs"

    def __init__(self, request_json_fn=None):
        self._request_json = request_json_fn
        if not hasattr(self, 'metadata'):
            self.metadata = {}
        if not hasattr(self, 'domains'):
            self.domains = []
        self.anikoto_url = "https://anikototv.to"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        }
        self._anime_page_cache = {}
        self._media_cache = {}

    @property
    def base_url(self) -> str:
        return self.domains[0] if getattr(self, 'domains', None) else "https://megaplay.buzz"

    @property
    def name(self) -> str:
        return self.metadata.get("name", "Anikoto")

    def _fetch_media(self, provider_id: str) -> dict[str, Any] | None:
        try:
            from ..core.storage import load_config
            from ..services.anilist_auth import stored_anilist_token
            token = stored_anilist_token(load_config())
        except Exception:
            token = ""
        try:
            res = anilist.fetch_one(urllib.request.urlopen, json.load, token, anilist_id=provider_id)
            if res:
                return res
        except Exception as e:
            _logger.debug("Anikoto fetch_one error: %s", e)
        return self._media_cache.get(str(provider_id))

    def search(self, query: str, ttype: str = "sub") -> list[dict[str, Any]]:
        try:
            from ..core.anilist_fallback import search_anilist_with_fallback
            res = search_anilist_with_fallback(query)
            media_list = res.get("data", {}).get("Page", {}).get("media", [])
            results = []
            for media in media_list:
                if "id" in media:
                    self._media_cache[str(media["id"])] = media
                titles = media.get("title") or {}
                main_name = titles.get("romaji") or titles.get("english") or "Unknown"
                ep_count = media.get("episodes") or 0
                results.append({
                    "_id": str(media["id"]),
                    "name": main_name,
                    "romajiName": titles.get("romaji") or "",
                    "englishName": titles.get("english") or "",
                    "nativeName": titles.get("native") or "",
                    "altNames": list(media.get("synonyms") or []),
                    "type": media.get("format") or "TV",
                    "format": media.get("format"),
                    "status": media.get("status"),
                    "season": {
                        "year": media.get("seasonYear"),
                        "name": media.get("season"),
                    },
                    "episodeCount": media.get("episodes"),
                    "score": media.get("averageScore"),
                    "genres": media.get("genres", []),
                    "description": media.get("description", ""),
                    "availableEpisodes": {
                        "sub": ep_count,
                        "dub": ep_count if ttype == "dub" else 0,
                        "raw": 0,
                    },
                    "thumbnail": (media.get("coverImage") or {}).get("large"),
                    "banner": media.get("bannerImage"),
                    "aniListId": str(media["id"]),
                    "malId": media.get("idMal"),
                })
            return normalize_titles(results, provider_id=self.id, provider_name=self.name, id_key="_id")
        except Exception as e:
            _logger.debug("Anikoto search error: %s", e)
            return []

    def get_title(self, provider_id: str) -> dict[str, Any] | None:
        try:
            media = self._fetch_media(provider_id)
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
            media = self._fetch_media(provider_id)
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
            
            detail = {
                "sub": ids,
                "dub": ids if ttype == "dub" else [],
                "raw": [],
            }
            return normalize_episode_catalog({"ids": ids, "detail": detail}, provider_id=self.id, provider_title_id=provider_id)
        except Exception as e:
            _logger.debug("Anikoto episode_catalog error: %s", e)
            return normalize_episode_catalog({"ids": []}, provider_id=self.id, provider_title_id=provider_id)

    def _extract_single_server(self, s_name: str, link_id: str, watch_url: str) -> list[dict[str, Any]]:
        results = []
        try:
            emb_api = f"{self.anikoto_url}/ajax/server?get={urllib.parse.quote(link_id)}"
            req_emb_api = urllib.request.Request(emb_api, headers={**self.headers, "Referer": watch_url, "X-Requested-With": "XMLHttpRequest"})
            emb_res = json.loads(urllib.request.urlopen(req_emb_api, timeout=5).read().decode('utf-8'))
            embed_url = emb_res.get("result", {}).get("url")
            if not embed_url:
                return []

            parsed_emb = urllib.parse.urlparse(embed_url)
            host = parsed_emb.netloc
            qs = urllib.parse.parse_qs(parsed_emb.query)

            req_emb_page = urllib.request.Request(embed_url, headers={"User-Agent": self.headers["User-Agent"], "Referer": f"{self.anikoto_url}/"})
            emb_page_html = urllib.request.urlopen(req_emb_page, timeout=5).read().decode('utf-8', errors='ignore')
            m_did = re.search(r'data-id=[\"\'](\d+)[\"\']', emb_page_html)
            if not m_did:
                return []
            d_id = m_did.group(1)

            stream_url = None
            tracks = []
            embed_referer = f"https://{host}/"

            if "vidtube" in host:
                src_api = f"https://vidtube.site/stream/getSources?id={d_id}"
                req_src = urllib.request.Request(src_api, headers={
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": embed_url,
                    "Origin": "https://vidtube.site",
                    "X-Requested-With": "XMLHttpRequest"
                })
                src_res = json.loads(urllib.request.urlopen(req_src, timeout=5).read().decode('utf-8'))
                sources = src_res.get("sources", {})
                stream_url = sources.get("file") if isinstance(sources, dict) else (sources[0].get("file") if sources else None)
                tracks = src_res.get("tracks", [])
            elif "megaplay" in host:
                s_param = qs.get("s", [""])[0]
                if not s_param:
                    s_param = "tcdn"

                def _fetch_megaplay_sources(target_s: str) -> dict | None:
                    api = f"https://megaplay.buzz/stream/getSourcesNew?id={d_id}"
                    if target_s:
                        api += f"&s={target_s}"
                    req = urllib.request.Request(api, headers={
                        "User-Agent": self.headers["User-Agent"],
                        "Referer": embed_url,
                        "Origin": "https://megaplay.buzz",
                        "X-Requested-With": "XMLHttpRequest"
                    })
                    try:
                        return json.loads(urllib.request.urlopen(req, timeout=6).read().decode('utf-8'))
                    except Exception:
                        api_old = f"https://megaplay.buzz/stream/getSources?id={d_id}"
                        if target_s:
                            api_old += f"&s={target_s}"
                        req_old = urllib.request.Request(api_old, headers={
                            "User-Agent": self.headers["User-Agent"],
                            "Referer": embed_url,
                            "Origin": "https://megaplay.buzz",
                            "X-Requested-With": "XMLHttpRequest"
                        })
                        try:
                            return json.loads(urllib.request.urlopen(req_old, timeout=6).read().decode('utf-8'))
                        except Exception:
                            return None

                src_res = None
                try:
                    src_res = _fetch_megaplay_sources(s_param)
                except Exception:
                    src_res = None

                if not src_res and s_param != "tcdn":
                    try:
                        src_res = _fetch_megaplay_sources("tcdn")
                    except Exception:
                        src_res = None

                if not src_res:
                    return []

                stream_url = None
                if src_res.get("enc"):
                    dec = _decrypt_megaplay_enc(src_res["enc"])
                    if dec and isinstance(dec, dict):
                        stream_url = dec.get("file") or dec.get("url")

                if not stream_url:
                    sources = src_res.get("sources", [])
                    if isinstance(sources, dict):
                        stream_url = sources.get("file")
                    elif isinstance(sources, list) and sources:
                        stream_url = sources[0].get("file") if isinstance(sources[0], dict) else None

                tracks = src_res.get("tracks", [])

                # If primary endpoint returned the blocked fetch.nexabloom.top domain,
                # retry with s=tcdn which yields working CDN hosts (megap.*)
                if not stream_url or "fetch.nexabloom.top" in stream_url:
                    try:
                        src_res_tcdn = _fetch_megaplay_sources("tcdn")
                        if src_res_tcdn and src_res_tcdn.get("enc"):
                            dec_tcdn = _decrypt_megaplay_enc(src_res_tcdn["enc"])
                            if dec_tcdn and isinstance(dec_tcdn, dict) and dec_tcdn.get("file"):
                                stream_url = dec_tcdn["file"]
                                if not tracks:
                                    tracks = src_res_tcdn.get("tracks", [])
                    except Exception:
                        pass

            if not stream_url:
                return []

            subtitles = []
            for track in tracks:
                if isinstance(track, dict) and track.get("file"):
                    subtitles.append({
                        "url": track["file"],
                        "label": track.get("label", "Unknown"),
                        "kind": track.get("kind", "captions"),
                        "default": bool(track.get("default")),
                    })
            default_sub = next((s["url"] for s in subtitles if s.get("default")), None)
            if not default_sub and subtitles:
                default_sub = next((s["url"] for s in subtitles if "eng" in s.get("label", "").lower()), subtitles[0]["url"])

            n = s_name.lower()
            if "vidplay" in n:
                priority_val = 1
            elif "vidstream" in n:
                priority_val = 2
            elif "hd-2" in n:
                priority_val = 3
            elif "hd-1" in n:
                priority_val = 10
            else:
                priority_val = 4

            # Master playlist variant parsing
            parsed_variants = False
            if stream_url.endswith(".m3u8"):
                try:
                    req_m = urllib.request.Request(stream_url, headers={
                        "User-Agent": self.headers["User-Agent"],
                        "Referer": embed_referer
                    })
                    m_txt = urllib.request.urlopen(req_m, timeout=5).read().decode('utf-8')
                    if "#EXT-X-STREAM-INF" in m_txt:
                        lines = m_txt.splitlines()
                        variants = []
                        for i, line in enumerate(lines):
                            if line.startswith("#EXT-X-STREAM-INF"):
                                res_match = re.search(r'RESOLUTION=\d+x(\d+)', line)
                                res_int = int(res_match.group(1)) if res_match else 0
                                quality = f"{res_int}p" if res_int else "auto"
                                if i + 1 < len(lines):
                                    uri = lines[i+1].strip()
                                    if uri and not uri.startswith("#"):
                                        v_url = urllib.parse.urljoin(stream_url, uri)
                                        v_entry = {
                                            "sourceName": f"{s_name} ({quality})",
                                            "streamUrl": v_url,
                                            "type": "hls",
                                            "priority": priority_val,
                                            "resolution": str(res_int) if res_int else "auto",
                                            "sort_key": res_int,
                                            "headers": {
                                                "Referer": embed_referer,
                                                "Origin": embed_referer.rstrip("/"),
                                                "User-Agent": self.headers["User-Agent"]
                                            }
                                        }
                                        if subtitles:
                                            v_entry["subtitles"] = subtitles
                                        if default_sub:
                                            v_entry["subtitle_url"] = default_sub
                                        variants.append(v_entry)
                        if variants:
                            variants.sort(key=lambda x: x["sort_key"], reverse=True)
                            for v in variants:
                                del v["sort_key"]
                                results.append(v)
                            parsed_variants = True
                except Exception as parse_e:
                    _logger.debug("Failed to parse variants for %s: %s", s_name, parse_e)

            auto_entry = {
                "sourceName": f"{s_name} (Auto)" if parsed_variants else s_name,
                "streamUrl": stream_url,
                "type": "hls" if stream_url.endswith(".m3u8") else "mp4",
                "priority": priority_val,
                "resolution": "auto",
                "headers": {
                    "Referer": embed_referer,
                    "Origin": embed_referer.rstrip("/"),
                    "User-Agent": self.headers["User-Agent"]
                }
            }
            if subtitles:
                auto_entry["subtitles"] = subtitles
            if default_sub:
                auto_entry["subtitle_url"] = default_sub
            results.append(auto_entry)
        except Exception as s_err:
            _logger.debug("Anikoto server %s extraction error: %s", s_name, s_err)
        return results

    def episode_sources(
        self,
        provider_id: str,
        episode: str,
        ttype: str = "sub",
    ) -> dict[str, Any] | None:
        source_urls = []
        seen_urls = set()

        # 1. Multi-Server Extraction via anikototv.to
        try:
            cache_key = (provider_id, ttype)
            anime_id, watch_url = self._anime_page_cache.get(cache_key, (None, None))

            if not anime_id or not watch_url:
                media = self._fetch_media(provider_id)
                if media:
                    titles = [media.get("title", {}).get(k) for k in ["english", "romaji", "userPreferred"] if media.get("title", {}).get(k)]
                    main_title = titles[0] if titles else ""

                    s_m = re.search(r'season\s*(\d+)|(\d+)(?:nd|rd|th)\s*season', main_title, re.I)
                    target_season = int(s_m.group(1) or s_m.group(2)) if s_m else 1

                    clean_q = re.sub(r'[^a-zA-Z0-9\s]', ' ', main_title)
                    short_q = ' '.join(clean_q.split()[:4])

                    search_url = f"{self.anikoto_url}/filter?keyword={urllib.parse.quote_plus(short_q)}"
                    req_search = urllib.request.Request(search_url, headers={**self.headers, "Referer": f"{self.anikoto_url}/"})
                    html_search = urllib.request.urlopen(req_search, timeout=6).read().decode('utf-8', errors='ignore')
                    soup_search = BeautifulSoup(html_search, "html.parser")

                    candidates = []
                    seen_candidates = set()
                    for a in soup_search.find_all("a", href=True):
                        if "/watch/" in a["href"] and a.text.strip():
                            txt = a.text.strip()
                            if not re.match(r'^\d+(\.\d+)?\s+(TV|Movie|Special|OVA|ONA)', txt) and not re.match(r'^\d+\s+\d+', txt):
                                if a["href"] not in seen_candidates:
                                    seen_candidates.add(a["href"])
                                    candidates.append((txt, a["href"]))

                    def _score_match(c_title: str, t_title: str, t_season: int) -> float:
                        c_norm = re.sub(r'[^a-z0-9]', '', c_title.lower())
                        t_norm = re.sub(r'[^a-z0-9]', '', t_title.lower())
                        if c_norm == t_norm:
                            return 100.0
                        if t_season:
                            if f'season{t_season}' in c_norm or f'{t_season}ndseason' in c_norm or f'{t_season}rdseason' in c_norm:
                                pass
                            elif t_season == 1 and not any(f'season{i}' in c_norm for i in range(2, 10)):
                                pass
                            else:
                                return 0.0
                        c_words = set(re.findall(r'[a-z0-9]+', c_title.lower()))
                        t_words = set(re.findall(r'[a-z0-9]+', t_title.lower()))
                        if not t_words:
                            return 0.0
                        overlap = len(c_words & t_words) / len(t_words)
                        extra_penalty = 0.0
                        for unwanted in ['special', 'specials', 'movie', 'oad', 'ova', 'reawakening']:
                            if unwanted in c_words and unwanted not in t_words:
                                extra_penalty += 0.3
                        return max(0.0, overlap - extra_penalty)

                    scored = [(max(_score_match(c_txt, t, target_season) for t in titles), c_txt, c_href) for c_txt, c_href in candidates]
                    scored.sort(key=lambda x: x[0], reverse=True)

                    if scored and scored[0][0] > 0.1:
                        best_href = scored[0][2]
                        watch_url = f"{self.anikoto_url}{best_href}" if best_href.startswith("/") else best_href

                        req_watch = urllib.request.Request(watch_url, headers={**self.headers, "Referer": f"{self.anikoto_url}/"})
                        w_html = urllib.request.urlopen(req_watch, timeout=6).read().decode('utf-8', errors='ignore')
                        w_soup = BeautifulSoup(w_html, "html.parser")
                        main_div = w_soup.find(id="watch-main")
                        anime_id = main_div.get("data-id") if main_div else None
                        if anime_id and watch_url:
                            self._anime_page_cache[cache_key] = (anime_id, watch_url)

            if anime_id and watch_url:
                ep_url = f"{self.anikoto_url}/ajax/episode/list/{anime_id}"
                req_ep = urllib.request.Request(ep_url, headers={**self.headers, "Referer": watch_url, "X-Requested-With": "XMLHttpRequest"})
                ep_res = json.loads(urllib.request.urlopen(req_ep, timeout=6).read().decode('utf-8'))
                ep_soup = BeautifulSoup(ep_res.get("result", ""), "html.parser")

                target_a = None
                for a in ep_soup.find_all("a"):
                    if a.get("data-number") == str(episode) or a.get("data-num") == str(episode) or a.get("data-slug") == str(episode):
                        target_a = a
                        break
                if not target_a:
                    all_a = ep_soup.find_all("a")
                    try:
                        ep_idx = int(episode) - 1
                        if 0 <= ep_idx < len(all_a):
                            target_a = all_a[ep_idx]
                    except Exception:
                        pass

                if target_a and target_a.get("data-ids"):
                    data_ids = target_a.get("data-ids")
                    sv_url = f"{self.anikoto_url}/ajax/server/list?servers={urllib.parse.quote(data_ids)}"
                    req_sv = urllib.request.Request(sv_url, headers={**self.headers, "Referer": watch_url, "X-Requested-With": "XMLHttpRequest"})
                    sv_res = json.loads(urllib.request.urlopen(req_sv, timeout=6).read().decode('utf-8'))
                    sv_soup = BeautifulSoup(sv_res.get("result", ""), "html.parser")

                    type_div = sv_soup.find("div", class_="type", attrs={"data-type": ttype.lower()})
                    if not type_div:
                        type_div = sv_soup

                    server_items = []
                    for li in type_div.find_all("li"):
                        s_name = li.text.strip()
                        link_id = li.get("data-link-id")
                        if link_id:
                            server_items.append((s_name, link_id))

                    def _server_rank(item):
                        n = item[0].lower()
                        if "vidplay" in n:
                            return 0
                        if "vidstream" in n:
                            return 1
                        if "hd-2" in n:
                            return 2
                        if "hd-1" in n:
                            return 99
                        return 3

                    server_items.sort(key=_server_rank)

                    if server_items:
                        try:
                            from allmanga_cli import app_core
                            s_names = ", ".join(s[0] for s in server_items[:4])
                            app_core.info(f"[{self.name}] Found {len(server_items)} servers ({s_names}) • Extracting streams...")
                        except Exception:
                            pass

                        from concurrent.futures import ThreadPoolExecutor, as_completed
                        with ThreadPoolExecutor(max_workers=min(4, len(server_items))) as pool:
                            futures = {
                                pool.submit(self._extract_single_server, s_name, link_id, watch_url): s_name
                                for s_name, link_id in server_items
                            }
                            for fut in as_completed(futures):
                                s_name = futures[fut]
                                try:
                                    entries = fut.result()
                                    added = 0
                                    for entry in entries:
                                        if entry.get("streamUrl") not in seen_urls:
                                            seen_urls.add(entry["streamUrl"])
                                            source_urls.append(entry)
                                            added += 1
                                    if added > 0:
                                        try:
                                            from allmanga_cli import app_core
                                            app_core.info(f"[{self.name}] Resolved {s_name} ({added} streams)")
                                        except Exception:
                                            pass
                                except Exception as err:
                                    _logger.debug("Server %s extraction failed: %s", s_name, err)
        except Exception as e:
            _logger.debug("Anikoto multi-server scraping error: %s", e)

        # 2. Fallback: Direct MegaPlay embed (if multi-server returned no sources)
        if not source_urls:
            try:
                embed_url = f"{self.base_url}/stream/ani/{provider_id}/{episode}/{ttype}"
                req_embed = urllib.request.Request(
                    embed_url,
                    headers={
                        **self.headers,
                        "Referer": f"{self.base_url}/",
                        "Accept": "text/html,application/json,text/plain,*/*"
                    }
                )
                html = urllib.request.urlopen(req_embed, timeout=7).read().decode('utf-8', errors='ignore')
                match = re.search(r'data-id=["\'](\d+)["\']', html)
                if match:
                    data_id = match.group(1)
                    api_url = f"{self.base_url}/stream/getSources?id={data_id}"
                    req_api = urllib.request.Request(
                        api_url,
                        headers={
                            **self.headers,
                            "Referer": embed_url,
                            "Origin": self.base_url,
                            "Accept": "application/json,text/plain,*/*",
                            "X-Requested-With": "XMLHttpRequest"
                        }
                    )
                    res_api = urllib.request.urlopen(req_api, timeout=7).read().decode('utf-8')
                    sources_data = json.loads(res_api)
                    enc_payload = sources_data.get("enc")
                    if enc_payload:
                        dec = _decrypt_megaplay_enc(enc_payload)
                        if isinstance(dec, dict):
                            if "tracks" in sources_data and "tracks" not in dec:
                                dec["tracks"] = sources_data["tracks"]
                            sources_data = dec
                        elif isinstance(dec, list):
                            sources_data = {"sources": dec, "tracks": sources_data.get("tracks", [])}

                    subtitles = []
                    for track in sources_data.get("tracks", []):
                        if isinstance(track, dict) and track.get("file"):
                            subtitles.append({
                                "url": track["file"],
                                "label": track.get("label", "Unknown"),
                                "kind": track.get("kind", "captions"),
                                "default": bool(track.get("default")),
                            })
                    default_sub = next((s["url"] for s in subtitles if s.get("default")), None)
                    if not default_sub and subtitles:
                        default_sub = next((s["url"] for s in subtitles if "eng" in s.get("label", "").lower()), subtitles[0]["url"])

                    raw_sources = sources_data.get("sources", [])
                    if isinstance(raw_sources, dict):
                        raw_sources = [raw_sources]
                    for source in raw_sources:
                        url = source.get("file") or source.get("url")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        fb_entry = {
                            "sourceName": "MegaPlay (Auto)",
                            "streamUrl": url,
                            "type": "hls" if url.endswith(".m3u8") else "mp4",
                            "priority": 1,
                            "resolution": "auto",
                            "headers": {
                                "Referer": f"{self.base_url}/",
                                "Origin": self.base_url,
                                "User-Agent": self.headers["User-Agent"]
                            }
                        }
                        if subtitles:
                            fb_entry["subtitles"] = subtitles
                        if default_sub:
                            fb_entry["subtitle_url"] = default_sub
                        source_urls.append(fb_entry)
            except Exception as fb_err:
                _logger.debug("Anikoto legacy fallback error: %s", fb_err)

        if not source_urls:
            return None

        return normalize_episode_sources(
            {"episode": {"sourceUrls": source_urls}},
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
        if episode:
            return f"{self.base_url}/stream/ani/{provider_id}/{episode}/{ttype}"
        return f"https://anilist.co/anime/{provider_id}"

PROVIDER_CLASS = AnikotoProvider
