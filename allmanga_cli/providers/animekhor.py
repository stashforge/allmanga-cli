"""AnimeKhor provider."""

from __future__ import annotations

from .animexin import AnimeXinProvider


class AnimeKhorProvider(AnimeXinProvider):
    id = "animekhor"
    name = "AnimeKhor"
    base_url = "https://animekhor.org"


PROVIDER_CLASS = AnimeKhorProvider
