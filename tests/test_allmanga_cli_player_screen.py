import os
import unittest
from io import StringIO
from unittest.mock import patch

from allmanga_cli.ui import player_screen


class FakePosterManager:
    def get(self, show):
        return "POSTER-LINE-1\nPOSTER-LINE-2"


class PlayerScreenTests(unittest.TestCase):
    def tearDown(self):
        player_screen._player_ui_state["active"] = False

    def test_playback_poster_is_not_rewritten_when_unchanged(self):
        player_screen.activate({"name": "Against the Gods"}, "43", 43)
        player_screen.update_stream_info({
            "mirror": "Rumble",
            "quality": "1280x534",
        })
        player_screen._player_ui_state["mpv_props"] = {
            "pause": False,
            "playback-time": 1,
            "duration": 100,
        }

        with patch.object(
                player_screen.os,
                "get_terminal_size",
                return_value=os.terminal_size((100, 30)),
        ), patch.object(player_screen.sys, "stdout", StringIO()) as stdout:
            player_screen.render(FakePosterManager(), enter_alt_screen_fn=lambda: None)
            first = stdout.getvalue()
            stdout.seek(0)
            stdout.truncate(0)

            player_screen._player_ui_state["mpv_props"]["playback-time"] = 2
            player_screen.render(FakePosterManager(), enter_alt_screen_fn=lambda: None)
            second = stdout.getvalue()

        self.assertIn("POSTER-LINE-1", first)
        self.assertNotIn("POSTER-LINE-1", second)
        self.assertIn("Playing", second)

    def test_playback_uses_tight_progress_and_current_stream_block(self):
        player_screen.activate({
            "name": "Against the Gods",
            "availableEpisodes": {"sub": 44},
            "genres": ["Action", "Fantasy"],
            "description": "A compact description for the playback screen.",
        }, "44", 44)
        player_screen.update_stream_info({
            "mirror": "Hardsub English Dailymotion",
            "quality": "1920x800",
        })
        player_screen._player_ui_state["mpv_props"] = {
            "pause": True,
            "playback-time": 371,
            "duration": 1131,
        }

        with patch.object(
                player_screen.os,
                "get_terminal_size",
                return_value=os.terminal_size((100, 30)),
        ), patch.object(player_screen.sys, "stdout", StringIO()) as stdout:
            player_screen.render(FakePosterManager(), enter_alt_screen_fn=lambda: None)
            output = stdout.getvalue()

        self.assertIn("Paused", output)
        self.assertIn("━━━━", output)
        self.assertIn("────", output)
        self.assertNotIn("████", output)
        self.assertIn("Currently playing", output)
        self.assertIn("Episode 44", output)
        self.assertIn("Episodes 44/?", output)
        self.assertIn("06:11 / 18:51", output)
        self.assertIn("-12:40", output)
        self.assertIn("Genres", output)
        self.assertIn("Action \u00b7 Fantasy", output)
        self.assertIn("Description", output)
        self.assertIn("compact description", output)
        self.assertGreater(
            output.find("Paused"),
            output.find("Hardsub English Dailymotion"),
        )
        self.assertGreater(output.find("06:11 / 18:51"), output.find("━━━━"))


if __name__ == "__main__":
    unittest.main()
