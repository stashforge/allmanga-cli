import unittest

from allmanga_cli.providers.schema import build_catalog, build_episode, build_title


class ProviderSchemaTests(unittest.TestCase):
    def test_build_title_fills_common_shape_and_provider_fields(self):
        title = build_title(
            provider="animexin",
            provider_name="AnimeXin",
            provider_id="https://animexin.dev/show/",
            name="Against the Gods",
            thumbnail="https://animexin.dev/poster.jpg",
            media_type="ONA",
            available_sub=43,
            genres="Action, Fantasy",
            anilist_id=None,
            mal_id=None,
            extra={"_provider_latest": "43"},
        )

        self.assertEqual(title["_id"], "https://animexin.dev/show/")
        self.assertEqual(title["id"], "https://animexin.dev/show/")
        self.assertEqual(title["name"], "Against the Gods")
        self.assertEqual(title["englishName"], "")
        self.assertEqual(title["availableEpisodes"], {"sub": 43, "dub": 0, "raw": 0})
        self.assertEqual(title["availableEpisodesDetail"], {"sub": [], "dub": [], "raw": []})
        self.assertEqual(title["genres"], ["Action", "Fantasy"])
        self.assertIsNone(title["aniListId"])
        self.assertIsNone(title["malId"])
        self.assertEqual(title["_provider"], "animexin")
        self.assertEqual(title["_provider_name"], "AnimeXin")
        self.assertEqual(title["_provider_latest"], "43")

    def test_build_episode_uses_url_id_and_display_label_separately(self):
        episode = build_episode(
            episode_id="https://animexin.dev/show-episode-43/",
            label="43",
            title="Against the Gods Episode 43",
            url="https://animexin.dev/show-episode-43/",
        )

        self.assertEqual(episode["id"], "https://animexin.dev/show-episode-43/")
        self.assertEqual(episode["label"], "43")
        self.assertEqual(episode["url"], "https://animexin.dev/show-episode-43/")
        self.assertEqual(episode["translationType"], "sub")

    def test_build_catalog_derives_compatibility_fields_from_episodes(self):
        catalog = build_catalog(
            provider="animexin",
            provider_id="https://animexin.dev/show/",
            episodes={
                "sub": [
                    {
                        "id": "https://animexin.dev/show-episode-43/",
                        "label": "43",
                        "title": "Against the Gods Episode 43",
                        "url": "https://animexin.dev/show-episode-43/",
                    }
                ],
                "dub": [],
            },
        )

        self.assertEqual(catalog["state"], "loaded")
        self.assertEqual(catalog["ids"], ["https://animexin.dev/show-episode-43/"])
        self.assertEqual(
            catalog["labels"],
            {"https://animexin.dev/show-episode-43/": "43"},
        )
        self.assertEqual(catalog["detail"]["sub"], ["https://animexin.dev/show-episode-43/"])
        self.assertEqual(catalog["episodes"]["sub"][0]["label"], "43")


if __name__ == "__main__":
    unittest.main()

