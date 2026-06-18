import unittest
from unittest.mock import MagicMock, patch

from allmanga_cli.app_core import (
    get_show_anilist_id,
    match_allanime_show_to_anilist,
    match_anilist_show_to_allanime,
)


class IdMatchingTests(unittest.TestCase):
    @patch("allmanga_cli.app_core.save_al_match")
    @patch("allmanga_cli.app_core._best_allanime_match")
    @patch("allmanga_cli.app_core.search_anime")
    @patch("allmanga_cli.app_core.get_allanime_show")
    @patch("allmanga_cli.app_core.get_al_match")
    def test_anilist_to_allanime_exact_provider_id_wins_before_fuzzy(
        self,
        mock_get_match,
        mock_get_show,
        mock_search,
        mock_best,
        mock_save,
    ):
        mock_get_match.return_value = {}
        mock_get_show.return_value = None
        mock_search.return_value = [
            {"_id": "wrong-title", "aniListId": "999", "name": "Perfect Title"},
            {"_id": "right-id", "aniListId": "123", "name": "Weaker Title"},
        ]

        result = match_anilist_show_to_allanime(
            {"_id": "123", "name": "Some Show"},
            "sub",
        )

        self.assertEqual(result["_id"], "right-id")
        self.assertEqual(result["_match_source"], "id")
        self.assertEqual(get_show_anilist_id(result), 123)
        mock_best.assert_not_called()

    @patch("allmanga_cli.app_core.save_al_match")
    @patch("allmanga_cli.app_core._best_allanime_match")
    @patch("allmanga_cli.app_core.search_anime")
    @patch("allmanga_cli.app_core.get_allanime_show")
    @patch("allmanga_cli.app_core.get_al_match")
    def test_anilist_to_allanime_rejects_conflicting_non_manual_stored_match(
        self,
        mock_get_match,
        mock_get_show,
        mock_search,
        mock_best,
        mock_save,
    ):
        mock_get_match.return_value = {
            "_id": "stored-fuzzy",
            "match_source": "fuzzy",
        }
        mock_get_show.return_value = {
            "_id": "stored-fuzzy",
            "aniListId": "999",
        }
        mock_search.return_value = [{"_id": "other", "aniListId": "777"}]
        mock_best.return_value = {"_id": "fresh-fuzzy"}

        result = match_anilist_show_to_allanime(
            {"_id": "123", "name": "Some Show"},
            "sub",
        )

        self.assertEqual(result["_id"], "fresh-fuzzy")
        self.assertEqual(result["_match_source"], "fuzzy")

    @patch("allmanga_cli.app_core.save_al_match")
    @patch("allmanga_cli.app_core._best_allanime_match")
    @patch("allmanga_cli.app_core.search_anime")
    @patch("allmanga_cli.app_core.get_allanime_show")
    @patch("allmanga_cli.app_core.get_al_match")
    def test_anilist_to_allanime_keeps_manual_stored_match_even_if_ids_conflict(
        self,
        mock_get_match,
        mock_get_show,
        mock_search,
        mock_best,
        mock_save,
    ):
        mock_get_match.return_value = {
            "_id": "stored-manual",
            "match_source": "manual",
        }
        mock_get_show.return_value = {
            "_id": "stored-manual",
            "aniListId": "999",
        }
        mock_search.return_value = [{"_id": "other", "aniListId": "777"}]
        mock_best.return_value = {"_id": "fresh-fuzzy"}

        result = match_anilist_show_to_allanime(
            {"_id": "123", "name": "Some Show"},
            "sub",
        )

        self.assertEqual(result["_id"], "stored-manual")
        self.assertEqual(result["_match_source"], "manual")

    @patch(
        "allmanga_cli.app_core.fetch_anilist_media",
        return_value={
            "id": 123,
            "episodes": 12,
            "averageScore": 85,
            "format": "TV",
            "title": {"romaji": "Exact ID Match"},
            "mediaListEntry": {
                "progress": 10,
                "status": "CURRENT",
                "score": 8.5,
            },
        },
    )
    @patch("allmanga_cli.app_core.save_source_anilist_match")
    def test_allanime_to_anilist_provider_id_fetches_media_first(
        self,
        mock_save,
        mock_fetch,
    ):
        result = match_allanime_show_to_anilist(
            MagicMock(),
            MagicMock(),
            {"_id": "aa1", "name": "Some Title", "aniListId": "123"},
            "token",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["aniListId"], "123")
        self.assertEqual(result["_anilist_progress"], 10)
        self.assertEqual(result["_anilist_list"], "CURRENT")
        self.assertEqual(result["_anilist_score"], 8.5)
        self.assertEqual(result["_match_source"], "id")
        mock_fetch.assert_called_once_with("token", "123")

    @patch("allmanga_cli.app_core.fetch_anilist_media")
    @patch("allmanga_cli.app_core._choose_confident_match")
    @patch("allmanga_cli.app_core.search_anilist")
    @patch("allmanga_cli.app_core.get_source_anilist_match")
    @patch("allmanga_cli.app_core.save_source_anilist_match")
    def test_allanime_to_anilist_rejects_conflicting_non_manual_stored_match(
        self,
        mock_save,
        mock_get_source,
        mock_search,
        mock_best,
        mock_fetch,
    ):
        mock_fetch.side_effect = Exception("not found")
        mock_get_source.return_value = {"_id": "999", "match_source": "stored"}
        mock_search.return_value = [{"_id": "999"}, {"_id": "888"}]
        mock_best.return_value = {"_id": "888"}

        result = match_allanime_show_to_anilist(
            MagicMock(),
            MagicMock(),
            {"_id": "aa1", "aniListId": "123", "name": "Query"},
            "token",
        )

        self.assertEqual(result["aniListId"], "888")
        self.assertEqual(result["_match_source"], "fuzzy")


if __name__ == "__main__":
    unittest.main()
