import unittest
from tests.app_namespace import load_app_namespace
from allmanga_cli.domain.tracking import tracking_status_for_progress
namespace = load_app_namespace()
looks_complete = namespace["playback_looks_complete"]
updates_history = namespace["playback_updates_history"]
minimum_played = namespace["minimum_played_for_completion"]
actively_advancing = namespace["playback_is_actively_advancing"]


class PlaybackCompletionTests(unittest.TestCase):
    def test_minimum_played_scales_for_short_episodes(self):
        self.assertEqual(minimum_played(240), 60)
        self.assertEqual(minimum_played(180), 45)
        self.assertEqual(minimum_played(1440), 300)

    def test_seek_to_end_does_not_complete(self):
        self.assertFalse(
            looks_complete("QUIT", 99, 1425, 1440, played_seconds=5)
        )

    def test_watching_ending_after_seek_can_complete(self):
        self.assertTrue(
            looks_complete("QUIT", 92, 1325, 1440, played_seconds=300)
        )

    def test_short_episode_can_complete_with_relative_watch_time(self):
        self.assertTrue(
            looks_complete("QUIT", 92, 220, 240, played_seconds=60)
        )

    def test_eof_still_requires_meaningful_playback(self):
        self.assertFalse(
            looks_complete("EOF", 100, 240, 240, played_seconds=5)
        )
        self.assertTrue(
            looks_complete("EOF", 100, 240, 240, played_seconds=60)
        )

    def test_history_uses_played_time_not_seek_position(self):
        self.assertFalse(
            updates_history("QUIT", 99, 1425, 1440, played_seconds=5)
        )
        self.assertTrue(
            updates_history("QUIT", 10, 120, 1440, played_seconds=30)
        )

    def test_paused_or_buffering_time_is_not_counted(self):
        base = {"playback-time": 30, "pause": False, "paused-for-cache": False}
        self.assertTrue(actively_advancing(base, True))
        self.assertFalse(
            actively_advancing({**base, "pause": True}, True)
        )
        self.assertFalse(
            actively_advancing({**base, "paused-for-cache": True}, True)
        )
        self.assertFalse(actively_advancing(base, False))

    def test_releasing_unknown_total_never_auto_completes_anilist(self):
        show = {
            "status": "RELEASING",
            "episodeCount": None,
            "availableEpisodes": {"sub": 8},
            "_anilist_list": "CURRENT",
        }

        self.assertIsNone(tracking_status_for_progress(show, 8))

    def test_finished_known_total_can_auto_complete_anilist(self):
        show = {
            "status": "FINISHED",
            "episodeCount": 12,
            "_anilist_list": "CURRENT",
        }

        self.assertEqual(tracking_status_for_progress(show, 12), "COMPLETED")


if __name__ == "__main__":
    unittest.main()
