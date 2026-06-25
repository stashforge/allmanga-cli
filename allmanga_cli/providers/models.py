"""Provider-neutral title helpers.

The app still uses plain dictionaries internally.  These helpers add a small
common contract that future providers can share without forcing a wider UI
rewrite.
"""

from __future__ import annotations

from typing import Any


def normalize_title(
    title: dict[str, Any] | None,
    *,
    provider_id: str,
    provider_name: str,
    id_key: str = "_id",
) -> dict[str, Any] | None:
    if not isinstance(title, dict):
        return None
    normalized = dict(title)
    source_id = str(normalized.get(id_key) or normalized.get("_provider_id") or "")
    normalized["_provider"] = provider_id
    normalized["_provider_id"] = source_id
    normalized["_provider_name"] = provider_name
    if source_id and not normalized.get("_id"):
        normalized["_id"] = source_id
    return normalized


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
    return normalized


def title_provider_id(title: dict[str, Any] | None) -> str:
    if not isinstance(title, dict):
        return ""
    return str(title.get("_provider_id") or title.get("_id") or "")


def normalize_episode_catalog(
    catalog: dict[str, Any] | None,
    *,
    provider_id: str,
    provider_title_id: str,
) -> dict[str, Any]:
    normalized = dict(catalog or {})
    ids = [str(episode) for episode in normalized.get("ids") or []]
    normalized["ids"] = ids
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
