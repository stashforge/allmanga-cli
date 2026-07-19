import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.app_namespace import load_app_namespace
from allmanga_cli.core import storage
from allmanga_cli.state import paths


class HistoryAniListRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.ns = load_app_namespace(reload=True)
        self.globals = self.ns["refresh_history_entry_from_anilist"].__globals__
        patcher = patch.object(
            paths, "HISTORY_PATH", str(Path(self.temp_dir.name) / "history.json")
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        storage.reset_caches()
        self.addCleanup(storage.reset_caches)

    def entry(self):
        return {
            "show": {
                "_id": "provider-1",
                "_anilist_id": "123",
                "_sync_enabled": True,
                "_anilist_progress": 12,
                "_anilist_list": "CURRENT",
                "name": "History Test",
            },
            "episode": "12",
            "translation_type": "sub",
            "last_synced_progress": 12,
            "timestamp": 100,
        }

    def test_refresh_updates_remote_progress_and_status(self):
        entry = self.entry()
        self.globals["fetch_anilist_media"] = lambda token, media_id: {
            "id": 123,
            "title": {"romaji": "History Test", "english": None, "native": None},
            "format": "TV",
            "episodes": 16,
            "status": "RELEASING",
            "averageScore": 79,
            "startDate": {"year": 2026, "month": 4, "day": 1},
            "endDate": {},
            "nextAiringEpisode": {
                "episode": 15,
                "timeUntilAiring": 3600,
            },
            "mediaListEntry": {
                "progress": 13,
                "status": "CURRENT",
            },
        }

        refreshed = self.ns["refresh_history_entry_from_anilist"](
            entry, "token"
        )

        self.assertTrue(refreshed)
        self.assertEqual(entry["show"]["_anilist_progress"], 13)
        self.assertEqual(entry["show"]["_anilist_list"], "CURRENT")
        self.assertEqual(entry["show"]["episodeCount"], 16)
        self.assertEqual(entry["show"]["_next_airing_ep"], 15)
        self.assertEqual(entry["last_synced_progress"], 12)

    def test_local_only_entry_is_not_refreshed(self):
        entry = self.entry()
        entry["show"]["_sync_enabled"] = False
        called = []
        self.globals["fetch_anilist_media"] = lambda *args: called.append(args)

        self.assertFalse(
            self.ns["refresh_history_entry_from_anilist"](entry, "token")
        )
        self.assertEqual(called, [])

    def test_refreshed_history_is_persisted(self):
        history = [self.entry()]

        self.assertTrue(self.ns["save_refreshed_history"](history))

        saved = json.loads(Path(paths.HISTORY_PATH).read_text())
        self.assertNotIn("_anilist_progress", saved[0]["show"])
        self.assertIsNot(storage._history_cache, history)

    def test_refreshed_history_strips_large_runtime_cache_fields(self):
        history = [self.entry()]
        history[0]["show"].update({
            "_poster_raw": "x" * 500_000,
            "_poster_status": "ready",
            "_poster_status_time": 123,
            "_poster_failed": True,
            "availableEpisodesDetail": {"sub": [str(i) for i in range(200)]},
        })

        self.assertTrue(self.ns["save_refreshed_history"](history))

        saved_show = json.loads(
            Path(paths.HISTORY_PATH).read_text()
        )[0]["show"]
        for key in (
            "_poster_raw",
            "_poster_status",
            "_poster_status_time",
            "_poster_failed",
            "availableEpisodesDetail",
        ):
            self.assertNotIn(key, saved_show)


if __name__ == "__main__":
    unittest.main()
