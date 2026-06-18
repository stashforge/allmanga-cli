import unittest

from allmanga_cli.domain.history import (
    filter_history_entries,
    format_history_entry,
    local_progress,
    playback_episode,
)


class HistoryDomainTests(unittest.TestCase):
    def test_local_progress_uses_sparse_episode_catalog_index(self):
        show = {
            "_id": "show-1",
            "_episode_ids": ["1", "2.5", "4", "7"],
        }
        entries = [{
            "show": {"_id": "show-1"},
            "episode": "4",
            "translation_type": "sub",
        }]

        self.assertEqual(local_progress(entries, show), 3)

    def test_playback_keeps_episode_when_resume_exists(self):
        entry = {
            "show": {"_id": "show-1"},
            "episode": "2.5",
            "translation_type": "sub",
        }

        episode = playback_episode(
            entry,
            episode_ids=["1", "2.5", "4"],
            resume_time=lambda show_id, episode_id: 42,
        )

        self.assertEqual(episode, "2.5")

    def test_playback_advances_by_catalog_index_without_resume(self):
        entry = {
            "show": {"_id": "show-1"},
            "episode": "2.5",
            "translation_type": "sub",
        }

        episode = playback_episode(
            entry,
            episode_ids=["1", "2.5", "4"],
            resume_time=lambda show_id, episode_id: 0,
        )

        self.assertEqual(episode, "4")

    def test_playback_does_not_skip_catalog_gaps(self):
        entry = {
            "show": {"_id": "show-1"},
            "episode": "3",
            "translation_type": "sub",
        }

        episode = playback_episode(
            entry,
            episode_ids=["1", "3", "6"],
            resume_time=lambda show_id, episode_id: 0,
        )

        self.assertEqual(episode, "6")

    def test_playback_stays_on_last_catalog_episode(self):
        entry = {
            "show": {"_id": "show-1"},
            "episode": "6",
            "translation_type": "sub",
        }

        episode = playback_episode(
            entry,
            episode_ids=["1", "3", "6"],
            resume_time=lambda show_id, episode_id: 0,
        )

        self.assertEqual(episode, "6")

    def test_history_row_is_title_only(self):
        entry = {
            "show": {
                "_id": "show-1",
                "name": "Tongari Boushi no Atelier",
                "episodeCount": 13,
            },
            "episode": "0",
            "translation_type": "sub",
            "timestamp": 100,
        }

        self.assertEqual(
            format_history_entry(
                entry,
                prepare_display_state=lambda show, ttype: None,
                get_local_progress=lambda show, ttype: 0,
                now=200,
            ),
            "Tongari Boushi no Atelier",
        )

    def test_airing_title_is_up_to_date_when_available_episodes_watched(self):
        up_to_date = {
            "show": {
                "_id": "show-1",
                "name": "Airing",
                "status": "RELEASING",
                "episodeCount": 13,
                "_next_airing_ep": 13,
            },
            "episode": "12",
            "translation_type": "sub",
        }
        active = {
            "show": {
                "_id": "show-2",
                "name": "Behind",
                "status": "RELEASING",
                "episodeCount": 13,
                "_next_airing_ep": 13,
            },
            "episode": "11",
            "translation_type": "sub",
        }

        filtered = filter_history_entries(
            [up_to_date, active],
            "Up to date",
            prepare_display_state=lambda show, ttype: None,
            get_local_progress=lambda show, ttype: int(
                "12" if show["_id"] == "show-1" else "11"
            ),
        )

        self.assertEqual(filtered, [up_to_date])


if __name__ == "__main__":
    unittest.main()
