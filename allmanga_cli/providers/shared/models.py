"""Provider-neutral title helpers.

The app still uses plain dictionaries internally.  These helpers add a small
common contract that future providers can share without forcing a wider UI
rewrite.
"""

from __future__ import annotations

from typing import Any

from .schema import build_catalog, build_title
from allmanga_cli.brain import AnimeBrain
from allmanga_cli.brain.core.models import EpisodeToken


_TITLE_SCHEMA_KEYS = {
    "_id", "id", "name", "englishName", "nativeName", "altNames",
    "thumbnail", "banner", "description", "type", "format", "status",
    "season", "airedStart", "airedEnd", "startDate", "endDate",
    "episodeCount", "availableEpisodes", "availableEpisodesDetail",
    "score", "genres", "tags", "aniListId", "malId",
    "_provider", "_provider_id", "_provider_name",
}


def _find_field(d: dict, *canonical_targets: str) -> Any:
    """Case-insensitive and separator-agnostic field extractor."""
    if not isinstance(d, dict):
        return None
    for target in canonical_targets:
        if target in d and d[target] is not None:
            return d[target]

    import re
    norm_map = {
        re.sub(r"[^a-z0-9]", "", str(k).casefold()): v
        for k, v in d.items()
        if v is not None
    }
    for target in canonical_targets:
        clean_target = re.sub(r"[^a-z0-9]", "", str(target).casefold())
        if clean_target in norm_map:
            return norm_map[clean_target]
    return None


def normalize_title(
    title: dict[str, Any] | None,
    *,
    provider_id: str,
    provider_name: str,
    id_key: str = "_id",
) -> dict[str, Any] | None:
    if not isinstance(title, dict):
        return None
    source_id = str(title.get(id_key) or title.get("_provider_id") or "")
    extra = {
        key: value
        for key, value in title.items()
        if key not in _TITLE_SCHEMA_KEYS
    }
    
    return build_title(
        provider=provider_id,
        provider_name=provider_name,
        provider_id=source_id,
        name=title.get("name") or "",
        english_name=title.get("englishName") or "",
        native_name=title.get("nativeName") or "",
        alt_names=title.get("altNames") or [],
        thumbnail=title.get("thumbnail") or "",
        banner=title.get("banner") or "",
        description=title.get("description") or "",
        media_type=title.get("type"),
        media_format=title.get("format"),
        status=title.get("status"),
        season=title.get("season") or {},
        aired_start=title.get("airedStart"),
        aired_end=title.get("airedEnd"),
        start_date=title.get("startDate"),
        end_date=title.get("endDate"),
        episode_count=title.get("episodeCount"),
        available_sub=(title.get("availableEpisodes") or {}).get("sub", 0),
        available_dub=(title.get("availableEpisodes") or {}).get("dub", 0),
        available_raw=(title.get("availableEpisodes") or {}).get("raw", 0),
        available_detail=title.get("availableEpisodesDetail") or {},
        score=title.get("score"),
        genres=title.get("genres") or [],
        tags=title.get("tags") or [],
        anilist_id=_find_field(title, "aniListId", "anilist_id", "anilist"),
        mal_id=_find_field(title, "malId", "idMal", "myanimelist_id", "mal"),
        extra=extra,
    )


def normalize_titles(
    titles,
    *,
    provider_id: str,
    provider_name: str,
    id_key: str = "_id",
) -> list[dict[str, Any]]:
    normalized = []
    for title in titles or []:
        item = normalize_title(
            title,
            provider_id=provider_id,
            provider_name=provider_name,
            id_key=id_key,
        )
        if item is not None:
            normalized.append(item)
            
    # Sort the results so same franchises are grouped together, 
    # and seasons are chronologically ordered!
    def get_sort_key(item):
        raw_name = item.get("name") or ""
        from allmanga_cli.brain import AnimeBrain
        bout = AnimeBrain.process(raw_name, dict)
        
        year = 0
        month = 0
        for d in [item.get("airedStart"), item.get("startDate")]:
            if isinstance(d, dict):
                year = d.get("year") or 0
                month = d.get("month") or 0
                break
            elif isinstance(d, str):
                parts = d.split('-')
                if parts[0].isdigit(): year = int(parts[0])
                if len(parts) > 1 and parts[1].isdigit(): month = int(parts[1])
                break
                
        # 1. Base Franchise (split by colon to group spin-offs and movies with the main series!)
        franchise = bout.get("franchise", "").lower()
        base_franchise = franchise.split(':')[0].strip() if ':' in franchise else franchise
        
        # 2. Year/Month (chronological watch order)
        # 3. Season/Part (fallback for same-month releases)
        # 4. Raw Name (alphabetical fallback for providers like AniDBApp that return 0 for all years)
        return (base_franchise, year == 0, year, month, bout.get("season") or 0, bout.get("part") or 0, raw_name)
        
    return sorted(normalized, key=get_sort_key)


def title_provider_id(title: dict[str, Any] | None) -> str:
    if not isinstance(title, dict):
        return ""
    return str(title.get("_provider_id") or title.get("_id") or "")


def title_provider_key(title: dict[str, Any] | None, default: str = "allanime") -> str:
    if not isinstance(title, dict):
        return default
    return str(title.get("_provider") or default)


def normalize_episode_catalog(
    catalog: dict[str, Any] | None,
    *,
    provider_id: str,
    provider_title_id: str,
) -> dict[str, Any]:
    normalized = dict(catalog or {})
    ids = [str(episode) for episode in normalized.get("ids") or []]
    built = build_catalog(
        provider=provider_id,
        provider_id=provider_title_id,
        state=normalized.get("state") or "loaded",
        error=normalized.get("error") or "",
        episodes={
            "sub": [
                {
                    "id": episode_id, 
                    "label": (AnimeBrain.process(episode_id, EpisodeToken) or type("Mock", (), {"raw_label": episode_id})()).raw_label or episode_id,
                    "number": getattr(AnimeBrain.process(episode_id, EpisodeToken), "absolute_number", 0.0) if AnimeBrain.process(episode_id, EpisodeToken) else 0.0
                }
                for episode_id in ids
            ],
            "dub": [],
            "raw": [],
        },
    )
    built.update(normalized)
    built["ids"] = ids
    if "labels" not in built:
        built["labels"] = {
            episode_id: AnimeBrain.process(episode_id, EpisodeToken).get('raw_label') or episode_id 
            for episode_id in ids
        }
    if "episodes" not in normalized:
        built["episodes"] = built.get("episodes") or {
            "sub": [],
            "dub": [],
            "raw": [],
        }
    normalized = built
    normalized["_provider"] = provider_id
    normalized["_provider_id"] = str(provider_title_id or "")
    normalized["_provider_episode_ids"] = ids
    return normalized


def normalize_episode_sources(
    payload: dict[str, Any] | None,
    *,
    provider_id: str,
    provider_title_id: str,
    episode: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    normalized = dict(payload)
    episode_data = dict(normalized.get("episode") or {})
    sources = list(episode_data.get("sourceUrls") or [])
    episode_data["sourceUrls"] = sources
    normalized["episode"] = episode_data
    normalized["_provider"] = provider_id
    normalized["_provider_id"] = str(provider_title_id or "")
    normalized["_provider_episode"] = str(episode)
    normalized["_provider_sources"] = sources
    return normalized
