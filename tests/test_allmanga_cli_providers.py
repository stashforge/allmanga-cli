import json
import unittest

from allmanga_cli.providers import ALLANIME, get_provider, provider_key
from allmanga_cli.providers.allanime import AllAnimeProvider
from allmanga_cli.providers.models import (
    normalize_episode_catalog,
    normalize_episode_sources,
    normalize_title,
    title_provider_key,
    title_provider_id,
)
from allmanga_cli.services import allanime as allanime_service


class ProviderRegistryTests(unittest.TestCase):
    def test_default_provider_is_allanime(self):
        self.assertIs(get_provider(), ALLANIME)
        self.assertIs(get_provider("allanime"), ALLANIME)

    def test_unknown_provider_falls_back_to_allanime(self):
        self.assertIs(get_provider("missing-provider"), ALLANIME)
        self.assertEqual(provider_key("missing-provider"), "allanime")

    def test_request_bound_provider_uses_same_registry_fallback(self):
        provider = get_provider("missing-provider", lambda *args, **kwargs: {})

        self.assertIsInstance(provider, AllAnimeProvider)
        self.assertIsNot(provider, ALLANIME)


class AllAnimeProviderTests(unittest.TestCase):
    def test_normalized_title_preserves_existing_shape_and_adds_provider_fields(self):
        title = normalize_title(
            {"_id": "show-id", "name": "Test"},
            provider_id="example",
            provider_name="Example",
        )

        self.assertEqual(title["_id"], "show-id")
        self.assertEqual(title["_provider_id"], "show-id")
        self.assertEqual(title["_provider"], "example")
        self.assertEqual(title["_provider_name"], "Example")
        self.assertEqual(title_provider_id(title), "show-id")
        self.assertEqual(title_provider_key(title), "example")

    def test_episode_catalog_adds_provider_fields_without_changing_ids(self):
        catalog = normalize_episode_catalog(
            {"state": "loaded", "ids": [1, "2.5"], "detail": {"sub": ["2.5", "1"]}},
            provider_id="example",
            provider_title_id="title-id",
        )

        self.assertEqual(catalog["ids"], ["1", "2.5"])
        self.assertEqual(catalog["_provider_episode_ids"], ["1", "2.5"])
        self.assertEqual(catalog["_provider"], "example")
        self.assertEqual(catalog["_provider_id"], "title-id")

    def test_episode_sources_adds_provider_fields_and_keeps_allanime_shape(self):
        source = {"sourceName": "Yt-mp4"}
        payload = normalize_episode_sources(
            {"episode": {"sourceUrls": [source]}},
            provider_id="example",
            provider_title_id="title-id",
            episode="6.5",
        )

        self.assertEqual(payload["episode"]["sourceUrls"], [source])
        self.assertEqual(payload["_provider_sources"], [source])
        self.assertEqual(payload["_provider_episode"], "6.5")
        self.assertEqual(payload["_provider"], "example")

    def test_browser_url_builds_show_and_episode_urls(self):
        provider = AllAnimeProvider()

        self.assertEqual(
            provider.browser_url(
                "srGrP23qJnjsHrRYD",
                "11",
                "sub",
                {"allanime_frontend_domain": "https://mkissa.to/"},
            ),
            "https://mkissa.to/anime/srGrP23qJnjsHrRYD/p-11-sub",
        )
        self.assertEqual(
            provider.browser_url(
                "show id",
                "6.5",
                "dub",
                {"allanime_frontend_domain": "https://mkissa.to/"},
            ),
            "https://mkissa.to/anime/show%20id/p-6.5-dub",
        )

    def test_browser_url_falls_back_for_invalid_domain_and_translation(self):
        provider = AllAnimeProvider()

        self.assertEqual(
            provider.browser_url(
                "show-id",
                "1",
                "bad-type",
                {"allanime_frontend_domain": "not a url"},
            ),
            "https://mkissa.to/anime/show-id/p-1-sub",
        )

    def test_service_calls_use_injected_request_function(self):
        calls = []

        def request_json(url, data=None, **kwargs):
            calls.append(url)
            payload = json.loads((data or b"{}").decode()) if data else {}
            query = payload.get("query", "")
            if "shows(" in query:
                return {"data": {"shows": {"edges": []}}}
            if "availableEpisodesDetail" in query:
                return {"data": {"show": {"availableEpisodesDetail": {"sub": ["1"]}}}}
            if "show(" in query:
                return {"data": {"show": {"_id": "show-id"}}}
            if "variables=" in url:
                return {"data": {"episode": {"sourceUrls": "encrypted"}}}
            return {"data": {}}

        provider = AllAnimeProvider(request_json_fn=request_json)
        original_decrypt = allanime_service.decrypt_tobeparsed

        try:
            allanime_service.decrypt_tobeparsed = lambda value: json.dumps(
                {"episode": {"sourceUrls": []}}
            )

            self.assertEqual(provider.search("slime"), [])
            self.assertEqual(
                provider.get_title("show-id"),
                {
                    "_id": "show-id",
                    "_provider": "allanime",
                    "_provider_id": "show-id",
                    "_provider_name": "AllAnime",
                },
            )
            self.assertEqual(
                provider.episode_catalog("show-id"),
                {
                    "state": "loaded",
                    "ids": ["1"],
                    "detail": {"sub": ["1"]},
                    "error": "",
                    "_provider": "allanime",
                    "_provider_id": "show-id",
                    "_provider_episode_ids": ["1"],
                },
            )
            self.assertEqual(
                provider.episode_sources("show-id", "1"),
                {
                    "episode": {"sourceUrls": []},
                    "_provider": "allanime",
                    "_provider_id": "show-id",
                    "_provider_episode": "1",
                    "_provider_sources": [],
                },
            )
        finally:
            allanime_service.decrypt_tobeparsed = original_decrypt

        self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
