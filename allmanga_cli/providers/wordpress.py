"""Reusable helpers for WordPress-style anime streaming sites."""

from __future__ import annotations

import base64
import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from ..services.http import UA


@dataclass(frozen=True)
class Entry:
    title: str
    url: str
    meta: str = ""


@dataclass(frozen=True)
class Mirror:
    label: str
    url: str
    embed_html: str = ""


@dataclass(frozen=True)
class EpisodePage:
    title: str
    series_title: str
    series_url: str
    mirrors: list[Mirror]


def fetch_html(url: str, *, timeout: int = 25) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def normalize_url(base_url: str, url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", url)


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def attr_value(attrs: str, name: str) -> str:
    match = re.search(rf'\b{name}=["\']([^"\']+)["\']', attrs, re.I)
    return html.unescape(match.group(1)) if match else ""


def is_episode_url(url: str) -> bool:
    return bool(re.search(r"/[^/]*episode[^/]*/?$", urllib.parse.urlparse(url).path))


def is_media_asset_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower()
    return path.endswith((
        ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp",
    ))


def parse_cards(base_url: str, page_html: str, *, only_main: bool = False) -> list[Entry]:
    source = page_html
    if only_main:
        start = page_html.find('<div class="listupd">')
        if start != -1:
            ends = [
                idx for idx in (
                    page_html.find('<div class="pagination"', start),
                    page_html.find('<div id="sidebar"', start),
                )
                if idx != -1
            ]
            source = page_html[start : min(ends) if ends else len(page_html)]

    entries: list[Entry] = []
    seen: set[str] = set()
    pattern = re.compile(r"<a\s+(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.I | re.S)
    for match in pattern.finditer(source):
        attrs = match.group("attrs")
        href_attr = attr_value(attrs, "href")
        if not href_attr:
            continue
        href = normalize_url(base_url, href_attr)
        if not href.startswith(base_url) or href in seen:
            continue
        if is_media_asset_url(href):
            continue
        title = attr_value(attrs, "title")
        if not title:
            headline = re.search(
                r"<h[234][^>]*>(.*?)</h[234]>",
                match.group("body"),
                re.I | re.S,
            )
            title = headline.group(1) if headline else match.group("body")
        title = clean_text(title)
        if not title or title in {"View All", "Next"}:
            continue
        seen.add(href)
        entries.append(Entry(title=title, url=href))
    return entries


def parse_series(base_url: str, page_html: str) -> list[Entry]:
    section = page_html
    match = re.search(
        r'<div class="episodelist">(.*?)</div>\s*</div>\s*</div>',
        page_html,
        re.S,
    )
    if match:
        section = match.group(1)
    items: list[Entry] = []
    seen: set[str] = set()
    item_pattern = re.compile(
        r'<li[^>]*>\s*<a\s+href=["\'](?P<href>[^"\']+)["\'][^>]*>'
        r"(?P<body>.*?)</a>\s*</li>",
        re.I | re.S,
    )
    for item in item_pattern.finditer(section):
        href = normalize_url(base_url, html.unescape(item.group("href")))
        if href in seen:
            continue
        title_match = re.search(r"<h3[^>]*>(.*?)</h3>", item.group("body"), re.I | re.S)
        meta_match = re.search(r"<span[^>]*>(.*?)</span>", item.group("body"), re.I | re.S)
        title = clean_text(title_match.group(1) if title_match else item.group("body"))
        if title:
            seen.add(href)
            items.append(Entry(
                title=title,
                url=href,
                meta=clean_text(meta_match.group(1)) if meta_match else "",
            ))
    return items


def parse_episode(base_url: str, page_html: str) -> EpisodePage:
    title_match = re.search(
        r'<h1[^>]*class=["\'][^"\']*entry-title[^"\']*["\'][^>]*>(.*?)</h1>',
        page_html,
        re.I | re.S,
    )
    title = clean_text(title_match.group(1)) if title_match else "Unknown episode"

    series_match = re.search(
        r'series\s+<a\s+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<title>.*?)</a>',
        page_html,
        re.I | re.S,
    )
    series_title = clean_text(series_match.group("title")) if series_match else ""
    series_url = normalize_url(base_url, series_match.group("href")) if series_match else ""

    return EpisodePage(
        title=title,
        series_title=series_title,
        series_url=series_url,
        mirrors=parse_mirrors(base_url, page_html),
    )


def parse_mirrors(base_url: str, page_html: str) -> list[Mirror]:
    mirrors: list[Mirror] = []
    seen: set[str] = set()
    option_pattern = re.compile(
        r'<option\s+[^>]*value=["\'](?P<value>[^"\']+)["\'][^>]*>'
        r"(?P<label>.*?)</option>",
        re.I | re.S,
    )
    for option in option_pattern.finditer(page_html):
        value = html.unescape(option.group("value")).strip()
        if not value:
            continue
        try:
            embed = base64.b64decode(value + "=" * (-len(value) % 4)).decode(
                "utf-8",
                errors="replace",
            )
        except Exception:
            continue
        src_match = re.search(r'\bsrc=["\'](?P<src>[^"\']+)["\']', embed, re.I)
        if not src_match:
            continue
        url = normalize_embed_url(normalize_url(base_url, html.unescape(src_match.group("src"))))
        if url in seen:
            continue
        seen.add(url)
        mirrors.append(Mirror(label=clean_text(option.group("label")), url=url, embed_html=embed.strip()))
    return mirrors


def normalize_embed_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host == "geo.dailymotion.com" and "/player/" in parsed.path:
        video_id = urllib.parse.parse_qs(parsed.query).get("video", [""])[0]
        if video_id:
            return f"https://www.dailymotion.com/video/{video_id}"
    if host.endswith("dailymotion.com"):
        match = re.search(r"/embed/video/([^/?#]+)", parsed.path)
        if match:
            return f"https://www.dailymotion.com/video/{match.group(1)}"
    if host == "odysee.com":
        decoded_path = urllib.parse.unquote(parsed.path)
        prefix = "/$/embed/"
        if decoded_path.startswith(prefix):
            return f"https://odysee.com/{decoded_path.removeprefix(prefix)}"
    if host == "play.d.tube":
        video_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
        if video_id:
            return f"https://nas2.d.tube/videos/{dtube_to_uuid(video_id)}/master.m3u8"
    return url


def dtube_to_uuid(video_id: str) -> str:
    if re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        video_id,
    ):
        return video_id
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    value = 0
    for char in video_id:
        index = alphabet.find(char)
        if index == -1:
            return video_id
        value = value * 58 + index
    hex_value = f"{value:032x}"
    return f"{hex_value[:8]}-{hex_value[8:12]}-{hex_value[12:16]}-{hex_value[16:20]}-{hex_value[20:32]}"


def episode_number(value: str, fallback: str = "") -> str:
    match = re.search(r"\b(?:episode|eps?)\s*[-:]?\s*(\d+(?:\.\d+)?)\b", value, re.I)
    return match.group(1) if match else fallback


class WordPressAnimeProvider:
    id = ""
    name = ""
    base_url = ""

    def __init__(self, fetch: Callable[[str], str] = fetch_html):
        self._fetch = fetch

    def search(self, query: str, ttype: str = "sub") -> list[dict]:
        del ttype
        url = f"{self.base_url}/?{urllib.parse.urlencode({'s': query})}"
        entries = [
            entry for entry in parse_cards(self.base_url, self._fetch(url), only_main=True)
            if not is_episode_url(entry.url)
        ]
        return [self._title_from_entry(entry) for entry in entries]

    def get_title(self, provider_id: str) -> dict | None:
        title = provider_id.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
        return self._title_from_entry(Entry(title=title, url=provider_id))

    def episode_catalog(self, provider_id: str, ttype: str = "sub") -> dict:
        del ttype
        entries = list(reversed(parse_series(self.base_url, self._fetch(provider_id))))
        ids = [entry.url for entry in entries]
        labels = {
            entry.url: episode_number(entry.title or entry.meta, str(index + 1))
            for index, entry in enumerate(entries)
        }
        return {
            "state": "loaded",
            "ids": ids,
            "labels": labels,
            "detail": {"sub": ids, "dub": []},
            "error": "",
        }

    def episode_sources(self, provider_id: str, episode: str, ttype: str = "sub") -> dict | None:
        del provider_id, ttype
        page = parse_episode(self.base_url, self._fetch(episode))
        sources = []
        for mirror in page.mirrors:
            stream_type = "hls" if ".m3u8" in mirror.url else "external"
            sources.append({
                "sourceName": mirror.label or self.name,
                "link": mirror.url,
                "type": stream_type,
                "resolution": "Adaptive",
                "referer": episode,
                "android_safe": stream_type == "hls",
            })
        return {"episode": {"sourceUrls": sources}}

    def browser_url(
        self,
        provider_id: str,
        episode: str | None = None,
        ttype: str = "sub",
        cfg: dict | None = None,
    ) -> str:
        del ttype, cfg
        return episode or provider_id or self.base_url

    def _title_from_entry(self, entry: Entry) -> dict:
        return {
            "_id": entry.url,
            "name": entry.title,
            "englishName": "",
            "nativeName": "",
            "altNames": [],
            "thumbnail": "",
            "type": "ONA",
            "season": {},
            "score": None,
            "availableEpisodes": {"sub": 0, "dub": 0},
            "status": "",
            "episodeCount": None,
        }
