import runpy
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"


class EpisodeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.ns = runpy.run_path(str(SCRIPT))
        self.globals = self.ns["ensure_episode_ids"].__globals__

    def test_loaded_catalog_preserves_real_ids_gaps_and_decimals(self):
        self.globals["_req"] = lambda *args, **kwargs: {
            "data": {
                "show": {
                    "availableEpisodesDetail": {
                        "sub": ["10", "6.5", "3", "1"],
                    }
                }
            }
        }
        show = {"_id": "provider-1", "availableEpisodes": {"sub": 10}}

        episode_ids = self.ns["ensure_episode_ids"](show, "sub")

        self.assertEqual(episode_ids, ["1", "3", "6.5", "10"])
        self.assertEqual(show["_episode_catalog_state"], "loaded")

    def test_network_failure_does_not_fabricate_contiguous_ids(self):
        def fail(*args, **kwargs):
            raise OSError("offline")

        self.globals["_req"] = fail
        show = {"_id": "provider-1", "availableEpisodes": {"sub": 12}}

        episode_ids = self.ns["ensure_episode_ids"](show, "sub")

        self.assertEqual(episode_ids, [])
        self.assertEqual(show["_episode_catalog_state"], "unavailable")
        self.assertNotIn("_episode_ids", show)

    def test_graphql_error_is_an_unavailable_catalog(self):
        self.globals["_req"] = lambda *args, **kwargs: {
            "errors": [{"message": "bad request"}],
            "data": {"show": None},
        }
        show = {"_id": "provider-1", "availableEpisodes": {"sub": 12}}

        self.assertEqual(self.ns["ensure_episode_ids"](show, "sub"), [])
        self.assertEqual(show["_episode_catalog_state"], "unavailable")

    def test_successful_empty_catalog_stays_empty(self):
        self.globals["_req"] = lambda *args, **kwargs: {
            "data": {
                "show": {
                    "availableEpisodesDetail": {"sub": []},
                }
            }
        }
        show = {"_id": "provider-1", "availableEpisodes": {"sub": 12}}

        self.assertEqual(self.ns["ensure_episode_ids"](show, "sub"), [])
        self.assertEqual(show["_episode_catalog_state"], "loaded")
        self.assertEqual(show["_episode_ids"], [])

    def test_legacy_contiguous_cache_is_explicit_when_refresh_fails(self):
        def fail(*args, **kwargs):
            raise OSError("offline")

        self.globals["_req"] = fail
        show = {
            "_id": "provider-1",
            "_episode_ids": ["1", "2", "3"],
            "_episode_ids_ttype": "sub",
        }

        episode_ids = self.ns["ensure_episode_ids"](show, "sub")

        self.assertEqual(episode_ids, ["1", "2", "3"])
        self.assertEqual(show["_episode_catalog_state"], "legacy_contiguous")

    def test_unknown_episode_id_does_not_guess_an_index(self):
        episode_ids = ["1", "2", "3.5", "6"]

        self.assertIsNone(
            self.ns["episode_index_for_id"](episode_ids, "4")
        )
        self.assertEqual(
            self.ns["episode_index_for_id"](episode_ids, "3.50"),
            2,
        )

    def test_empty_catalog_does_not_invent_episode_one(self):
        self.assertIsNone(self.ns["episode_id_at"]([], 0))

    def test_progress_beyond_catalog_does_not_clamp_to_last_episode(self):
        show = {
            "_id": "provider-1",
            "_episode_ids": ["1", "3", "6.5"],
            "_episode_ids_ttype": "sub",
            "_episode_catalog_state": "loaded",
        }

        self.assertIsNone(
            self.ns["episode_id_for_progress"](show, "sub", 4)
        )


if __name__ == "__main__":
    unittest.main()
