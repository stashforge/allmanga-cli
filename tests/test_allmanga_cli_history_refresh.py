import json
import tempfile
import unittest
from pathlib import Path

from tests.app_namespace import load_app_namespace


class HistoryAniListRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.ns = load_app_namespace(reload=True)
        self.globals = self.ns["refresh_history_entry_from_anilist"].__globals__
        self.globals["HISTORY_PATH"] = str(
            Path(self.temp_dir.name) / "history.json"
        )
        self.globals["_history_cache"] = None

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

        saved = json.loads(Path(self.globals["HISTORY_PATH"]).read_text())
        self.assertEqual(saved[0]["show"]["_anilist_progress"], 12)
        self.assertIs(self.globals["_history_cache"], history)


if __name__ == "__main__":
    unittest.main()
