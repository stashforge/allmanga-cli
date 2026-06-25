"""AnimeXin provider."""

from __future__ import annotations

from .models import normalize_episode_catalog, normalize_episode_sources, normalize_titles
from .wordpress import WordPressAnimeProvider, fetch_html


class AnimeXinProvider(WordPressAnimeProvider):
    id = "animexin"
    name = "AnimeXin"
    base_url = "https://animexin.dev"

    def __init__(self, request_json_fn=None, fetch=None):
        del request_json_fn
        super().__init__(fetch=fetch or fetch_html)

    def search(self, query: str, ttype: str = "sub") -> list[dict]:
        return normalize_titles(
            super().search(query, ttype),
            provider_id=self.id,
            provider_name=self.name,
        )

    def get_title(self, provider_id: str) -> dict | None:
        title = super().get_title(provider_id)
        if not title:
            return None
        return normalize_titles(
            [title],
            provider_id=self.id,
            provider_name=self.name,
        )[0]

    def episode_catalog(self, provider_id: str, ttype: str = "sub") -> dict:
        return normalize_episode_catalog(
            super().episode_catalog(provider_id, ttype),
            provider_id=self.id,
            provider_title_id=provider_id,
        )

    def episode_sources(self, provider_id: str, episode: str, ttype: str = "sub") -> dict | None:
        return normalize_episode_sources(
            super().episode_sources(provider_id, episode, ttype),
            provider_id=self.id,
            provider_title_id=provider_id,
            episode=episode,
        )


PROVIDER_CLASS = AnimeXinProvider
