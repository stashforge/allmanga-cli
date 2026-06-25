"""Streaming provider registry."""

from .allanime import AllAnimeProvider


ALLANIME = AllAnimeProvider()

PROVIDERS = {
    ALLANIME.id: ALLANIME,
}

PROVIDER_FACTORIES = {
    ALLANIME.id: AllAnimeProvider,
}


def provider_key(provider_id="allanime"):
    key = str(provider_id or "").casefold()
    return key if key in PROVIDERS else ALLANIME.id


def get_provider(provider_id="allanime", request_json_fn=None):
    key = provider_key(provider_id)
    if request_json_fn is None:
        return PROVIDERS[key]
    return PROVIDER_FACTORIES[key](request_json_fn)
