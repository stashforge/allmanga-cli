import runpy
import threading
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"


class StreamGenerationTests(unittest.TestCase):
    def setUp(self):
        self.ns = runpy.run_path(str(SCRIPT))
        self.globals = self.ns["start_bg_resolve"].__globals__
        with self.globals["_streams_lock"]:
            self.globals["all_streams"].clear()
            self.globals["_streams_generation"] = 0
        with self.globals["_bg_lock"]:
            self.globals["_bg_thread"] = None
            self.globals["_bg_generation"] = 0
            self.globals["_bg_stats"] = {
                "resolved": 0, "failed": 0, "total": 0, "current": ""
            }

    @staticmethod
    def episode(source_name):
        return {"episode": {"sourceUrls": [{"sourceName": source_name}]}}

    def test_stale_worker_cannot_publish_after_episode_switch(self):
        started = threading.Event()
        release = threading.Event()

        def resolve_source(src, silent=False):
            started.set()
            self.assertTrue(release.wait(2))
            return [{"link": "https://old.invalid/video", "source_name": "old"}]

        self.globals["resolve_source"] = resolve_source
        self.ns["_clear_streams"]()
        self.ns["start_bg_resolve"](self.episode("old"), set())
        old_thread = self.globals["_bg_thread"]
        self.assertTrue(started.wait(2))

        self.ns["_clear_streams"]()
        release.set()
        old_thread.join(2)

        self.assertFalse(old_thread.is_alive())
        self.assertEqual(self.ns["_stream_snapshot"](), [])

    def test_new_resolver_run_supersedes_old_worker_and_stats(self):
        old_started = threading.Event()
        release_old = threading.Event()

        def resolve_source(src, silent=False):
            name = src["sourceName"]
            if name == "old":
                old_started.set()
                self.assertTrue(release_old.wait(2))
            return [{"link": f"https://{name}.invalid/video", "source_name": name}]

        self.globals["resolve_source"] = resolve_source
        self.ns["_clear_streams"]()
        self.ns["start_bg_resolve"](self.episode("old"), set())
        old_thread = self.globals["_bg_thread"]
        self.assertTrue(old_started.wait(2))

        self.ns["start_bg_resolve"](self.episode("new"), set())
        new_thread = self.globals["_bg_thread"]
        new_thread.join(2)
        release_old.set()
        old_thread.join(2)

        self.assertEqual(
            [stream["link"] for stream in self.ns["_stream_snapshot"]()],
            ["https://new.invalid/video"],
        )
        self.assertEqual(
            self.globals["_bg_stats"],
            {"resolved": 1, "failed": 0, "total": 1, "current": ""},
        )


if __name__ == "__main__":
    unittest.main()
