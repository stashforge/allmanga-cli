import unittest
from pathlib import Path

from tests.app_namespace import load_app_namespace
APP = Path(__file__).resolve().parents[1] / "allmanga_cli" / "app.py"
namespace = load_app_namespace()


class AniListSortTests(unittest.TestCase):
    def shows(self):
        return [
            {
                "_id": "1",
                "name": "Zulu",
                "_anilist_progress": 2,
                "_anilist_updated_at": 100,
            },
            {
                "_id": "2",
                "name": "Alpha",
                "_anilist_progress": 8,
                "_anilist_updated_at": 300,
            },
            {
                "_id": "3",
                "name": "Middle",
                "_anilist_progress": 5,
                "_anilist_updated_at": 200,
            },
        ]

    def test_recent_prefers_latest_local_or_anilist_activity(self):
        history = [
            {
                "show": {"_anilist_id": "1"},
                "timestamp": 400,
            }
        ]

        sorted_shows = namespace["sort_anilist_shows"](
            self.shows(), "recent", history
        )

        self.assertEqual([show["_id"] for show in sorted_shows], ["1", "2", "3"])

    def test_anilist_mode_restores_original_order(self):
        shows = self.shows()

        self.assertEqual(
            namespace["sort_anilist_shows"](shows, "anilist"),
            shows,
        )

    def test_title_and_progress_modes_are_deterministic(self):
        shows = self.shows()

        by_title = namespace["sort_anilist_shows"](shows, "title")
        by_progress = namespace["sort_anilist_shows"](shows, "progress")

        self.assertEqual(
            [show["name"] for show in by_title],
            ["Alpha", "Middle", "Zulu"],
        )
        self.assertEqual(
            [show["_anilist_progress"] for show in by_progress],
            [8, 5, 2],
        )

    def test_sort_cycle_and_invalid_config_default(self):
        next_mode = namespace["next_anilist_sort_mode"]
        previous_mode = namespace["previous_anilist_sort_mode"]
        normalize = namespace["normalize_anilist_sort_mode"]

        self.assertEqual(normalize("unknown"), "recent")
        self.assertEqual(next_mode("recent"), "anilist")
        self.assertEqual(next_mode("anilist"), "title")
        self.assertEqual(next_mode("title"), "progress")
        self.assertEqual(next_mode("progress"), "recent")
        self.assertEqual(previous_mode("recent"), "progress")
        self.assertEqual(previous_mode("progress"), "title")
        self.assertEqual(previous_mode("title"), "anilist")
        self.assertEqual(previous_mode("anilist"), "recent")

    def test_sort_labels_are_user_facing(self):
        label = namespace["anilist_sort_label"]

        self.assertEqual(label("anilist"), "List Order")
        self.assertEqual(label("title"), "Title A-Z")
        self.assertEqual(label("title", reverse=True), "Title Z-A")
        self.assertEqual(label("progress"), "Progress ↓")
        self.assertEqual(label("progress", reverse=True), "Progress ↑")

    def test_anilist_list_query_requests_entry_update_time(self):
        source = (
            APP.parent / "services" / "anilist.py"
        ).read_text(encoding="utf-8")

        self.assertIn("progress\n            updatedAt", source)
        self.assertIn(
            'show["_anilist_updated_at"] = entry.get("updatedAt")',
            source,
        )


if __name__ == "__main__":
    unittest.main()
