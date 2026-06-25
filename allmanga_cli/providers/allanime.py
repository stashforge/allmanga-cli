"""AllAnime provider adapter."""

from __future__ import annotations

import urllib.parse
from typing import Any

from ..media.urls import validate_http_url
from ..services import allanime as allanime_service
from ..services.http import request_json
from .models import (
    normalize_episode_catalog,
    normalize_episode_sources,
    normalize_title,
    normalize_titles,
)


class AllAnimeProvider:
    id = "allanime"
    name = "AllAnime"

    def __init__(self, request_json_fn=request_json):
        self._request_json = request_json_fn

    def search(self, query: str, ttype: str = "sub") -> list[dict[str, Any]]:
        results = allanime_service.search_anime(self._request_json, query, ttype)
        return normalize_titles(
            results,
            provider_id=self.id,
            provider_name=self.name,
        )

    def get_title(self, provider_id: str) -> dict[str, Any] | None:
        return normalize_title(
            allanime_service.get_show(self._request_json, provider_id),
            provider_id=self.id,
            provider_name=self.name,
        )

    def episode_catalog(self, provider_id: str, ttype: str = "sub") -> dict[str, Any]:
        return normalize_episode_catalog(
            allanime_service.fetch_episode_catalog(
                self._request_json,
                provider_id,
                ttype,
            ),
            provider_id=self.id,
            provider_title_id=provider_id,
        )

    def episode_sources(
        self,
        provider_id: str,
        episode: str,
        ttype: str = "sub",
    ) -> dict[str, Any] | None:
        return normalize_episode_sources(
            allanime_service.get_episode_data(
                self._request_json,
                provider_id,
                episode,
                ttype,
            ),
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
        base = _frontend_domain(cfg)
        provider_id = str(provider_id or "").strip()
        if not provider_id:
            return base
        encoded_id = urllib.parse.quote(provider_id, safe="")
        if episode is None or str(episode).strip() == "":
            return f"{base}/anime/{encoded_id}"
        safe_ttype = str(ttype or "sub").strip().lower()
        if safe_ttype not in ("sub", "dub", "raw"):
            safe_ttype = "sub"
        encoded_episode = urllib.parse.quote(str(episode).strip(), safe="")
        return f"{base}/anime/{encoded_id}/p-{encoded_episode}-{safe_ttype}"


def _frontend_domain(cfg: dict[str, Any] | None = None) -> str:
    default = "https://mkissa.to"
    candidate = str((cfg or {}).get("allanime_frontend_domain") or default).strip()
    try:
        return validate_http_url(candidate).rstrip("/")
    except ValueError:
        return default
