import json
import unittest

from allmanga_cli.providers import ALLANIME, get_provider
from allmanga_cli.providers.allanime import AllAnimeProvider
from allmanga_cli.services import allanime as allanime_service


class ProviderRegistryTests(unittest.TestCase):
    def test_default_provider_is_allanime(self):
        self.assertIs(get_provider(), ALLANIME)
        self.assertIs(get_provider("allanime"), ALLANIME)

    def test_unknown_provider_falls_back_to_allanime(self):
        self.assertIs(get_provider("missing-provider"), ALLANIME)


class AllAnimeProviderTests(unittest.TestCase):
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
            self.assertEqual(provider.get_title("show-id"), {"_id": "show-id"})
            self.assertEqual(
                provider.episode_catalog("show-id"),
                {
                    "state": "loaded",
                    "ids": ["1"],
                    "detail": {"sub": ["1"]},
                    "error": "",
                },
            )
            self.assertEqual(
                provider.episode_sources("show-id", "1"),
                {"episode": {"sourceUrls": []}},
            )
        finally:
            allanime_service.decrypt_tobeparsed = original_decrypt

        self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
