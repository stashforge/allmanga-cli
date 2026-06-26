"""LuciferDonghua provider."""

from __future__ import annotations

from .animexin import AnimeXinProvider


class LuciferDonghuaProvider(AnimeXinProvider):
    id = "lucifer"
    name = "LuciferDonghua"
    base_url = "https://luciferdonghua.in"


PROVIDER_CLASS = LuciferDonghuaProvider
