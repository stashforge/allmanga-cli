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

        self.assertIn("EP", format_progress(anime))
        self.assertIn("8/12", format_progress(anime))

    def test_unknown_total_does_not_render_question_mark(self):
        anime = {
            "_sync_enabled": True,
            "_anilist_progress": 8,
            "episodeCount": None,
        }

        progress = format_progress(anime)

        self.assertIn("EP", progress)
        self.assertIn("8", progress)
        self.assertNotIn("?", progress)

    def test_unknown_total_does_not_use_available_as_total(self):
        anime = {
            "_sync_enabled": True,
            "_anilist_progress": 11,
            "episodeCount": None,
            "status": "RELEASING",
            "_next_airing_ep": 12,
        }

        line = format_info_metadata_line(anime)

        self.assertIn("EP", line)
        self.assertIn(" 11", line)
        self.assertIn("Avail 11", line)
        self.assertNotIn("11/11", line)

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

        self.assertIn("EP", line)
        self.assertIn("8/12", line)
        self.assertIn("Avail 8", line)
        self.assertIn("Next EP 9 in 1h", line)
        self.assertIn("ONA", line)
        self.assertIn("2026 -", line)
        self.assertIn("★ 8.1", line)

    def test_metadata_line_shows_anilist_and_anime_statuses(self):
        anime = {
            "_sync_enabled": True,
            "_anilist_list": "CURRENT",
            "_anilist_progress": 10,
            "episodeCount": 13,
            "status": "RELEASING",
            "type": "TV",
            "airedStart": {"year": 2026},
        }

        line = format_info_metadata_line(anime)

        self.assertLess(line.index("AL WATCHING"), line.index("AIRING"))
        self.assertIn("EP", line)
        self.assertIn("10/13", line)

    def test_anilist_status_stays_visible_when_sync_is_off(self):
        anime = {
            "_sync_enabled": False,
            "_anilist_list": "CURRENT",
            "_anilist_progress": 10,
            "episodeCount": 13,
            "status": "RELEASING",
        }

        line = format_info_metadata_line(anime)

        self.assertIn("AL WATCHING", line)

    def test_matching_anilist_list_status_can_be_hidden(self):
        anime = {
            "_sync_enabled": False,
            "_anilist_list": "CURRENT",
            "_anilist_progress": 10,
            "episodeCount": 13,
            "status": "RELEASING",
        }

        line = format_info_metadata_line(anime, hide_anilist_status="WATCHING")

        self.assertNotIn("AL WATCHING", line)
        self.assertIn("AIRING", line)
        self.assertIn("10/13", line)

    def test_different_anilist_status_stays_visible_when_hiding_current_list(self):
        anime = {
            "_sync_enabled": False,
            "_anilist_list": "PAUSED",
            "_anilist_progress": 3,
            "episodeCount": 13,
            "status": "FINISHED",
        }

        line = format_info_metadata_line(anime, hide_anilist_status="CURRENT")

        self.assertIn("AL PAUSED", line)

    def test_anilist_context_uses_anilist_progress_when_sync_is_off(self):
        anime = {
            "_sync_enabled": False,
            "_anilist_context": True,
            "_anilist_list": "CURRENT",
            "_anilist_progress": 6,
            "_local_progress": 2,
            "episodeCount": 13,
            "status": "FINISHED",
        }

        line = format_info_metadata_line(anime)

        self.assertIn("AL WATCHING", line)
        self.assertIn("EP", line)
        self.assertIn("6/13", line)
        self.assertNotIn("2/13", line)

    def test_anime_status_uses_quieter_color_than_anilist_status(self):
        anime = {
            "_sync_enabled": True,
            "_anilist_list": "CURRENT",
            "_anilist_progress": 1,
            "status": "RELEASING",
        }

        line = format_info_metadata_line(anime)

        self.assertIn("\033[32mAL WATCHING", line)
        self.assertIn("\033[38;5;250mAIRING", line)


if __name__ == "__main__":
    unittest.main()
