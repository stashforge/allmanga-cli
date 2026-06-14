import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"


class IncognitoModeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.ns = runpy.run_path(str(SCRIPT))
        self.globals = self.ns["is_incognito"].__globals__
        self.globals["INCOGNITO_MODE"] = True
        self.globals["DEBUG_MODE"] = False
        root = Path(self.temp_dir.name)
        self.paths = {
            "PLAYBACK_PATH": root / "playback.json",
            "HISTORY_PATH": root / "history.json",
            "SEARCH_HISTORY_PATH": root / "search_history.json",
            "ANILIST_QUEUE_PATH": root / "anilist_queue.json",
            "LOG_DIR": root / "logs",
        }
        for name, path in self.paths.items():
            self.globals[name] = str(path)
        self.globals["_prefs_cache"] = None
        self.globals["_history_cache"] = None
        self.globals["_search_history_cache"] = None
        self.globals["_anilist_queue_cache"] = None

    def tearDown(self):
        self.ns["_cleanup_incognito_cache"]()

    def test_playback_state_writes_leave_existing_files_untouched(self):
        playback = self.paths["PLAYBACK_PATH"]
        history = self.paths["HISTORY_PATH"]
        playback.write_text('{"existing": true}\n')
        history.write_text("[]\n")
        show = {"_id": "show-1", "_episode_ids": ["1"], "name": "Test"}

        self.ns["save_resume_time"]("show-1", "1", 90)
        self.ns["save_pending_completion"]("show-1", "1", 1, "2", 90, 1200)
        self.ns["save_history"](show, "1", "sub")

        self.assertEqual(playback.read_text(), '{"existing": true}\n')
        self.assertEqual(history.read_text(), "[]\n")

    def test_search_links_and_anilist_queue_are_not_persisted(self):
        show = {"_id": "show-1", "name": "Source"}
        anilist = {"_id": "123", "name": "Tracking"}

        self.ns["save_search_history"]("private query")
        self.ns["save_source_anilist_match"](show, anilist)
        queued = self.ns["queue_anilist_progress"](
            "token", "Tracking", 1, 123, show, "sub"
        )

        self.assertIsNone(queued)
        self.assertFalse(self.paths["SEARCH_HISTORY_PATH"].exists())
        self.assertFalse(self.paths["PLAYBACK_PATH"].exists())
        self.assertFalse(self.paths["ANILIST_QUEUE_PATH"].exists())

    def test_anilist_mutation_is_blocked_before_network(self):
        with patch.object(
            self.globals["anilist_service"],
            "update_entry",
            side_effect=AssertionError("network mutation attempted"),
        ):
            self.assertFalse(
                self.ns["update_anilist_entry"]("token", 123, progress=2)
            )

    def test_cover_cache_is_private_and_temporary(self):
        cache_dir = Path(self.ns["cover_cache_dir"]())
        self.assertTrue(cache_dir.is_dir())
        self.assertIn("allmanga-cli-incognito-", cache_dir.name)

        self.ns["_cleanup_incognito_cache"]()

        self.assertFalse(cache_dir.exists())

    def test_logs_are_suppressed_unless_debug_is_explicit(self):
        self.assertIsNone(self.ns["write_private_log"]("crash.log", "secret"))
        self.assertFalse(self.paths["LOG_DIR"].exists())

        self.globals["DEBUG_MODE"] = True
        path = self.ns["write_private_log"]("crash.log", "debug trace")
        self.assertEqual(Path(path).read_text(), "debug trace\n")

    def test_resume_is_ignored_and_metadata_shows_indicator(self):
        self.paths["PLAYBACK_PATH"].write_text(
            '{"show-1": {"resumes": {"1": 90}}}\n'
        )
        self.assertEqual(self.ns["get_resume_time"]("show-1", 1), 0)

        parts = []
        show = {
            "_id": "show-1",
            "name": "Private Show",
            "type": "TV",
            "airedStart": {"year": 2026},
        }
        self.ns["build_info_panel"](show, "sub", 80, parts)
        self.assertIn("INCOGNITO", parts[2])


if __name__ == "__main__":
    unittest.main()
