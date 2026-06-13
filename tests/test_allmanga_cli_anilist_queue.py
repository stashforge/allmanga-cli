import json
import runpy
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"


class AniListQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.ns = runpy.run_path(str(SCRIPT))
        self.globals = self.ns["queue_anilist_progress"].__globals__
        root = Path(self.temp_dir.name)
        self.globals["ANILIST_QUEUE_PATH"] = str(root / "anilist_queue.json")
        self.globals["PLAYBACK_PATH"] = str(root / "playback.json")
        self.globals["HISTORY_PATH"] = str(root / "history.json")
        self.globals["_anilist_queue_cache"] = None
        self.globals["_prefs_cache"] = None
        self.globals["_history_cache"] = None

    def tearDown(self):
        self.ns["flush_anilist_writes"](2)

    def show(self):
        return {
            "_id": "provider-1",
            "_anilist_id": 123,
            "_episode_ids": ["1", "2", "3"],
            "_anilist_progress": 0,
            "name": "Queue Test",
        }

    def queue_file(self):
        path = Path(self.globals["ANILIST_QUEUE_PATH"])
        return json.loads(path.read_text()) if path.exists() else []

    def test_mutation_is_persisted_before_network_and_removed_after_success(self):
        started = threading.Event()
        release = threading.Event()

        def scrobble(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(2))
            return True

        self.globals["scrobble_anilist"] = scrobble
        self.ns["queue_anilist_progress"](
            "token", "Queue Test", 1, 123, self.show(), "sub", "CURRENT"
        )

        self.assertTrue(started.wait(2))
        self.assertEqual(self.queue_file()[0]["progress"], 1)
        queue_mode = stat.S_IMODE(
            Path(self.globals["ANILIST_QUEUE_PATH"]).stat().st_mode
        )
        self.assertEqual(queue_mode, 0o600)
        release.set()
        self.assertTrue(self.ns["flush_anilist_writes"](2))
        self.assertEqual(self.queue_file(), [])

    def test_failed_mutation_remains_and_retries_next_run(self):
        self.globals["scrobble_anilist"] = lambda *args, **kwargs: False
        self.ns["queue_anilist_progress"](
            "token", "Queue Test", 2, 123, self.show(), "sub", "CURRENT"
        )
        self.assertTrue(self.ns["flush_anilist_writes"](2))

        queued = self.queue_file()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["attempts"], 1)

        self.globals["scrobble_anilist"] = lambda *args, **kwargs: True
        self.assertEqual(self.ns["retry_queued_anilist_writes"]("token"), 1)
        self.assertTrue(self.ns["flush_anilist_writes"](2))
        self.assertEqual(self.queue_file(), [])

    def test_progress_mutations_run_in_submission_order(self):
        observed = []

        def scrobble(token, title, progress, **kwargs):
            observed.append(progress)
            return True

        self.globals["scrobble_anilist"] = scrobble
        show = self.show()
        self.ns["queue_anilist_progress"](
            "token", "Queue Test", 1, 123, show, "sub", "CURRENT"
        )
        self.ns["queue_anilist_progress"](
            "token", "Queue Test", 2, 123, show, "sub", "CURRENT"
        )

        self.assertTrue(self.ns["flush_anilist_writes"](2))
        self.assertEqual(observed, [1, 2])
        self.assertEqual(self.queue_file(), [])

    def test_shutdown_flush_is_bounded(self):
        release = threading.Event()

        def scrobble(*args, **kwargs):
            self.assertTrue(release.wait(2))
            return True

        self.globals["scrobble_anilist"] = scrobble
        self.ns["queue_anilist_progress"](
            "token", "Queue Test", 1, 123, self.show(), "sub", "CURRENT"
        )

        started_at = time.monotonic()
        self.assertFalse(self.ns["flush_anilist_writes"](0.05))
        self.assertLess(time.monotonic() - started_at, 0.5)
        release.set()
        self.assertTrue(self.ns["flush_anilist_writes"](2))

    def test_pending_completion_is_kept_until_retry_succeeds(self):
        show = self.show()
        self.ns["save_resume_time"]("provider-1", "1", 600)
        self.ns["save_pending_completion"](
            "provider-1", "1", 1, "2", 600, 1400
        )
        self.globals["scrobble_anilist"] = lambda *args, **kwargs: False

        self.ns["queue_anilist_progress"](
            "token", "Queue Test", 1, 123, show, "sub", "CURRENT",
            pending_completion={"show_id": "provider-1", "episode": "1"},
        )
        self.assertTrue(self.ns["flush_anilist_writes"](2))
        self.assertEqual(
            self.ns["get_pending_completion"]("provider-1")["episode"], "1"
        )
        self.assertEqual(self.ns["get_resume_time"]("provider-1", "1"), 600)

        self.globals["scrobble_anilist"] = lambda *args, **kwargs: True
        self.ns["retry_queued_anilist_writes"]("token")
        self.assertTrue(self.ns["flush_anilist_writes"](2))
        self.assertEqual(self.ns["get_pending_completion"]("provider-1"), {})
        self.assertEqual(self.ns["get_resume_time"]("provider-1", "1"), 0)

    def test_newer_progress_keeps_older_pending_completion_marker(self):
        self.globals["scrobble_anilist"] = lambda *args, **kwargs: False
        show = self.show()
        self.ns["queue_anilist_progress"](
            "token", "Queue Test", 1, 123, show, "sub", "CURRENT",
            pending_completion={"show_id": "provider-1", "episode": "1"},
        )
        self.assertTrue(self.ns["flush_anilist_writes"](2))

        self.ns["queue_anilist_progress"](
            "token", "Queue Test", 2, 123, show, "sub", "CURRENT"
        )
        self.assertTrue(self.ns["flush_anilist_writes"](2))

        queued = self.queue_file()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["progress"], 2)
        self.assertEqual(
            queued[0]["pending_completion"],
            {"show_id": "provider-1", "episode": "1"},
        )


if __name__ == "__main__":
    unittest.main()
