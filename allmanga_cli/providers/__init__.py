"""Streaming provider registry."""

from .allanime import AllAnimeProvider


ALLANIME = AllAnimeProvider()

PROVIDERS = {
    ALLANIME.id: ALLANIME,
}


def get_provider(provider_id="allanime"):
    return PROVIDERS.get(str(provider_id or "").casefold(), ALLANIME)

