import runpy
import stat
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"
namespace = runpy.run_path(str(SCRIPT))
create_mpv_runtime = namespace["create_mpv_runtime"]
cleanup_mpv_runtime = namespace["cleanup_mpv_runtime"]
MpvIpc = namespace["MpvIpc"]
episode_transition_osd = namespace["episode_transition_osd"]
prefetch_matches_request = namespace["prefetch_matches_request"]
TRANSITION_OSD_MS = namespace["TRANSITION_OSD_MS"]


class MpvRuntimeTests(unittest.TestCase):
    def test_runtime_paths_are_unique_private_and_cleanable(self):
        first = create_mpv_runtime()
        second = create_mpv_runtime()
        self.addCleanup(cleanup_mpv_runtime, first[0])
        self.addCleanup(cleanup_mpv_runtime, second[0])

        self.assertNotEqual(first[0], second[0])
        for runtime_dir, socket_path, conf_path in (first, second):
            runtime = Path(runtime_dir)
            config = Path(conf_path)
            self.assertEqual(stat.S_IMODE(runtime.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
            self.assertEqual(Path(socket_path).parent, runtime)
            self.assertEqual(config.parent, runtime)
            self.assertIn("script-message next_ep", config.read_text())

        cleanup_mpv_runtime(first[0])
        self.assertFalse(Path(first[0]).exists())

    def test_mpv_runtime_creation_is_lazy(self):
        ipc = MpvIpc()

        self.assertIsNone(ipc.runtime_dir)
        self.assertIsNone(ipc.socket_path)
        self.assertIsNone(ipc.conf_path)

    def test_episode_transition_messages_match_direction(self):
        self.assertEqual(
            episode_transition_osd("NEXT", "loading"),
            "Loading next episode...",
        )
        self.assertEqual(
            episode_transition_osd("PREV", "loading"),
            "Loading previous episode...",
        )
        self.assertEqual(
            episode_transition_osd("NEXT", "starting"),
            "Next episode is ready\nStarting next episode...",
        )
        self.assertEqual(
            episode_transition_osd("PREV", "starting"),
            "Previous episode is ready\nStarting previous episode...",
        )
        self.assertEqual(
            episode_transition_osd("PREV", "failed"),
            "Previous episode is not available",
        )

    def test_prefetch_must_match_requested_episode(self):
        self.assertTrue(prefetch_matches_request(4, 4))
        self.assertTrue(prefetch_matches_request("4", 4))
        self.assertFalse(prefetch_matches_request(5, 4))
        self.assertFalse(prefetch_matches_request(None, 4))

    def test_transition_message_duration_is_persistent(self):
        self.assertGreaterEqual(TRANSITION_OSD_MS, 60 * 60 * 1000)


if __name__ == "__main__":
    unittest.main()
