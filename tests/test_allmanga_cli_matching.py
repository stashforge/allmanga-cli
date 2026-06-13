import runpy
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"
namespace = runpy.run_path(str(SCRIPT))
choose_match = namespace["_choose_confident_match"]
match_details = namespace["_match_score_details"]


def anime(name, *, year=None, episodes=None, anime_type="TV", english=None):
    return {
        "_id": name,
        "name": name,
        "englishName": english,
        "type": anime_type,
        "season": {"year": year} if year else {},
        "episodeCount": episodes,
    }


class MatchingTests(unittest.TestCase):
    def test_year_metadata_alone_cannot_match_unrelated_title(self):
        reference = anime("Frieren", year=2026, episodes=12)
        unrelated = anime("One Piece", year=2026, episodes=12)

        self.assertIsNone(choose_match(reference, [unrelated]))

    def test_single_result_is_still_scored(self):
        reference = anime("Frieren", year=2026)
        unrelated = anime("Completely Different", year=2026)

        self.assertIsNone(choose_match(reference, [unrelated]))

    def test_season_word_order_variation_matches(self):
        reference = anime(
            "Tensei Shitara Slime Datta Ken 4th Season",
            year=2026,
            episodes=12,
        )
        candidate = anime(
            "Tensei Shitara Slime Datta Ken Season 4",
            year=2026,
            episodes=12,
        )

        self.assertIs(choose_match(reference, [candidate]), candidate)

    def test_joined_and_spaced_romanization_matches(self):
        reference = anime("Wu Shen Zhu Zai", year=2023)
        candidate = anime("Wushen Zhuzai", year=2023)

        self.assertIs(choose_match(reference, [candidate]), candidate)

    def test_conflicting_season_numbers_are_rejected(self):
        reference = anime("My Hero Academia Season 4", year=2019)
        candidate = anime("My Hero Academia Season 5", year=2019)

        details = match_details(reference, candidate)

        self.assertEqual(details["contradiction"], "season")
        self.assertIsNone(choose_match(reference, [candidate]))

    def test_close_candidates_require_manual_choice(self):
        reference = anime("Example Anime", year=2024, episodes=12)
        first = anime("Example Anime", year=2024, episodes=12)
        second = anime("Example Anime", year=2024, episodes=12)

        self.assertIsNone(choose_match(reference, [first, second]))

    def test_clear_winner_beats_weaker_candidate(self):
        reference = anime("Sousou no Frieren", year=2023, episodes=28)
        correct = anime("Sousou no Frieren", year=2023, episodes=28)
        weaker = anime("Sousou no Frieren Specials", year=2023, episodes=4)

        self.assertIs(choose_match(reference, [weaker, correct]), correct)


if __name__ == "__main__":
    unittest.main()
