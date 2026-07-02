import unittest
from io import StringIO
from unittest.mock import patch

import allmanga_cli.app_core as app_core
from allmanga_cli.domain.episodes import (
    detect_next_episode_gap,
    episode_index_for_id,
    episode_label,
    episode_progress_number,
    highest_episode_number,
    parse_episode_label,
)
from allmanga_cli.domain.history import (
    history_available_episode_count,
    history_entry_progress,
)
from allmanga_cli.domain.metadata import format_progress


def _noop_prepare(show, ttype):
    pass


def _get_progress(value):
    def _inner(show, ttype):
        return value

    return _inner


def _entry(episode_ids, watched_episode, episode_count=None, ttype="sub"):
    show = {
        "_episode_ids": episode_ids,
        "_episode_ids_ttype": ttype,
        "availableEpisodes": {ttype: str(highest_episode_number(episode_ids))},
        "episodeCount": str(episode_count) if episode_count else None,
        "status": "RELEASING",
    }
    return {
        "episode": watched_episode,
        "show": show,
        "translation_type": ttype,
    }, show


def _next_episode(episode_ids, current):
    current_idx = episode_index_for_id(episode_ids, current)
    if current_idx is not None and current_idx + 1 < len(episode_ids):
        return episode_ids[current_idx + 1]
    return None


class EpisodeLabelTests(unittest.TestCase):
    def test_episode_label_uses_provider_label_for_url_episode_ids(self):
        labels = {"https://animexin.dev/show-part-3/": "Part 3"}

        self.assertEqual(
            episode_label("https://animexin.dev/show-part-3/", labels),
            "Part 3",
        )
        self.assertEqual(episode_label("2", {"2": "2"}), "Episode 2")

    def test_legacy_player_screen_uses_display_episode_label(self):
        app_core._player_ui_state.update({
            "active": True,
            "show": {"name": "Against the Gods"},
            "current_ep": "https://animexin.dev/against-the-gods-episode-43/",
            "current_ep_label": "43",
            "total_eps": 43,
            "status_lines": [],
            "stream_info": {},
            "mpv_props": None,
        })

        with patch.object(app_core, "enter_alt_screen"), \
                patch.object(app_core, "_get_player_poster", return_value=""), \
                patch.object(app_core.os, "get_terminal_size", return_value=app_core.os.terminal_size((100, 30))), \
                patch.object(app_core.sys, "stdout", StringIO()) as stdout:
            app_core.render_player_screen()

        output = stdout.getvalue()
        self.assertIn("Avail 43/?", output)
        self.assertNotIn("https://animexin.dev/against-the-gods-episode-43/", output)
        app_core._player_ui_state["active"] = False

    def test_parse_episode_label_handles_decimal_and_integer_labels(self):
        decimal_label = parse_episode_label("24.5")
        self.assertFalse(decimal_label["is_integer_like"])
        self.assertEqual(decimal_label["floor"], 24)
        self.assertEqual(decimal_label["ceil"], 25)

        integer_label = parse_episode_label("203")
        self.assertTrue(integer_label["is_integer_like"])
        self.assertEqual(integer_label["floor"], 203)
        self.assertEqual(integer_label["ceil"], 203)

    def test_highest_episode_number_keeps_decimal_when_it_is_highest(self):
        self.assertEqual(
            highest_episode_number(["1", "2", "24", "24.5", "25"]),
            25,
        )
        self.assertEqual(
            str(highest_episode_number(["1", "2", "24.5"])),
            "24.5",
        )

    def test_gap_detection_skips_missing_integer_range_but_not_decimal_specials(self):
        self.assertEqual(detect_next_episode_gap("3", "6"), (True, "missing 4-5"))
        self.assertEqual(detect_next_episode_gap("24", "24.5"), (False, ""))
        self.assertEqual(detect_next_episode_gap("24.5", "25"), (False, ""))

    def test_history_display_uses_real_episode_label_and_season_total(self):
        entry, show = _entry(["1", "2", "3", "6"], "3", episode_count=12)

        self.assertEqual(history_available_episode_count(entry), 6)
        local_idx = episode_index_for_id(show["_episode_ids"], "3")
        show["_local_progress"] = local_idx + 1
        show["_local_episode_label"] = "3"

        label, progress, total = history_entry_progress(
            entry,
            prepare_display_state=_noop_prepare,
            get_local_progress=_get_progress(local_idx + 1),
        )

        self.assertEqual(progress, "3")
        self.assertEqual(total, 12)
        self.assertIn("3/12", format_progress(show, local_only=True, ttype="sub"))
        self.assertEqual(_next_episode(show["_episode_ids"], "3"), "6")

    def test_doupo_style_catalog_uses_label_not_catalog_index(self):
        episode_ids = [str(i) for i in range(1, 201)]
        episode_ids[-1] = "203"
        entry, show = _entry(episode_ids, "203", episode_count=209)

        self.assertEqual(history_available_episode_count(entry), 203)
        self.assertEqual(highest_episode_number(episode_ids), 203)

        local_idx = episode_index_for_id(episode_ids, "203")
        show["_local_progress"] = local_idx + 1
        show["_local_episode_label"] = "203"

        label, progress, total = history_entry_progress(
            entry,
            prepare_display_state=_noop_prepare,
            get_local_progress=_get_progress(local_idx + 1),
        )

        self.assertEqual(progress, "203")
        self.assertEqual(total, 209)
        self.assertIn("203/209", format_progress(show, local_only=True, ttype="sub"))
        self.assertIsNone(_next_episode(episode_ids, "203"))

    def test_save_and_sync_watched_syncs_decimal_episode_floor_to_anilist(self):
        calls = []
        saved_history = []

        def sync(token, title, progress, media_id, show, ttype):
            calls.append(progress)
            return True

        def save_history(show, episode, ttype):
            saved_history.append(episode)

        with patch.object(app_core, "sync_watched_to_anilist", sync), patch.object(
            app_core,
            "save_history",
            save_history,
        ):
            show = {"_id": "test", "_anilist_progress": 0}
            result = app_core.save_and_sync_watched(
                show,
                "24.5",
                "sub",
                "token",
                "title",
                "24.5",
                "123",
            )

        self.assertEqual(calls, [24])
        self.assertEqual(saved_history, ["24.5"])
        self.assertEqual(result, {"status": "synced", "anilist_target": 24})
        self.assertEqual(
            show["_action_feedback"],
            "Saved locally as EP 24.5. AniList synced as EP 24.",
        )

    def test_mark_next_uses_next_catalog_label_not_contiguous_guess(self):
        episode_ids = ["1", "2", "3", "6"]
        next_id = _next_episode(episode_ids, "3")
        self.assertEqual(next_id, "6")
        self.assertEqual(episode_progress_number(next_id, 0), 6)


if __name__ == "__main__":
    unittest.main()
