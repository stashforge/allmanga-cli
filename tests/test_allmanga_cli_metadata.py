import unittest

from allmanga_cli.domain.metadata import (
    format_available_episodes,
    format_info_metadata_line,
    format_next_airing,
    format_progress,
    format_years,
    should_refresh_anilist,
)


class MetadataFormattingTests(unittest.TestCase):
    def test_synced_progress_uses_anilist_value_and_known_total(self):
        anime = {
            "_sync_enabled": True,
            "_anilist_progress": 8,
            "episodeCount": 12,
        }

        self.assertIn("AL", format_progress(anime))
        self.assertIn("Watched 8/12", format_progress(anime))

    def test_unknown_total_does_not_render_question_mark(self):
        anime = {
            "_sync_enabled": True,
            "_anilist_progress": 8,
            "episodeCount": None,
        }

        progress = format_progress(anime)

        self.assertIn("Watched 8", progress)
        self.assertNotIn("?", progress)

    def test_available_count_only_appears_for_releasing_anime(self):
        releasing = {
            "status": "RELEASING",
            "_next_airing_ep": 10,
        }
        finished = {
            "status": "FINISHED",
            "availableEpisodes": {"sub": 12},
        }

        self.assertEqual(
            format_available_episodes(releasing, ttype="sub"),
            "Avail 9",
        )
        self.assertEqual(
            format_available_episodes(finished, ttype="sub"),
            "",
        )

    def test_next_airing_uses_absolute_timestamp(self):
        anime = {
            "_next_airing_ep": 9,
            "_next_airing_at": 10_000,
            "_next_airing_time": 999_999,
        }

        self.assertEqual(
            format_next_airing(anime, now=6_400),
            "Next EP 9 in 1h",
        )
        self.assertEqual(
            format_next_airing(anime, now=10_001),
            "Next EP 9 aired",
        )

    def test_year_ranges_follow_airing_state(self):
        self.assertEqual(format_years(2022, 2022, "FINISHED"), "2022")
        self.assertEqual(format_years(2022, 2023, "FINISHED"), "2022 - 2023")
        self.assertEqual(format_years(2026, None, "RELEASING"), "2026 -")

    def test_expired_releasing_item_requires_refresh(self):
        anime = {
            "status": "RELEASING",
            "_next_airing_at": 100,
        }

        self.assertTrue(should_refresh_anilist(anime, now=101))
        self.assertFalse(should_refresh_anilist(anime, now=99))

    def test_metadata_line_keeps_type_year_and_score(self):
        anime = {
            "_sync_enabled": True,
            "_anilist_progress": 8,
            "episodeCount": 12,
            "status": "RELEASING",
            "_next_airing_ep": 9,
            "_next_airing_at": 10_000,
            "type": "ONA",
            "airedStart": {"year": 2026},
            "score": 8.1,
        }

        line = format_info_metadata_line(anime, now=6_400)

        self.assertIn("Watched 8/12", line)
        self.assertIn("Avail 8", line)
        self.assertIn("Next EP 9 in 1h", line)
        self.assertIn("ONA", line)
        self.assertIn("2026 -", line)
        self.assertIn("★ 8.1", line)


if __name__ == "__main__":
    unittest.main()
