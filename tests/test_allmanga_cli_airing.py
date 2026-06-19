import datetime as dt
import unittest

from allmanga_cli.domain.airing import (
    airing_row_label,
    airing_rows,
    filter_airing_shows,
    next_airing_tab,
    previous_airing_tab,
)


class AniListAiringTests(unittest.TestCase):
    def setUp(self):
        tz = dt.datetime.now().astimezone().tzinfo
        self.now = dt.datetime(2026, 6, 19, 10, 0, tzinfo=tz)

    def show(self, title, offset_hours, ep=1):
        airing_at = int((self.now + dt.timedelta(hours=offset_hours)).timestamp())
        return {
            "name": title,
            "_next_airing_ep": ep,
            "_next_airing_at": airing_at,
        }

    def test_tabs_filter_by_local_day(self):
        today = self.show("Today Show", 2, 11)
        tomorrow = self.show("Tomorrow Show", 26, 12)
        later = self.show("Later Show", 72, 13)
        shows = [later, tomorrow, today]

        self.assertEqual(
            [show["name"] for show in filter_airing_shows(shows, "today", self.now)],
            ["Today Show"],
        )
        self.assertEqual(
            [show["name"] for show in filter_airing_shows(shows, "tomorrow", self.now)],
            ["Tomorrow Show"],
        )
        self.assertEqual(
            [show["name"] for show in filter_airing_shows(shows, "week", self.now)],
            ["Today Show", "Tomorrow Show", "Later Show"],
        )

    def test_week_rows_group_days_without_selectable_headers(self):
        first = self.show("First", 2, 11)
        second = self.show("Second", 4, 12)
        tomorrow = self.show("Tomorrow", 26, 13)

        rows = airing_rows([tomorrow, second, first], "week", self.now)
        labels = [label for _show, label in rows]

        self.assertIn("Today", labels[0])
        self.assertNotIn("Today", labels[1])
        self.assertIn("Tomorrow", labels[2])
        self.assertIn("EP 11", labels[0])

    def test_today_row_uses_local_time_and_episode(self):
        label = airing_row_label(self.show("Witch Hat", 2, 11), tab="today", now=self.now)

        self.assertIn("EP 11", label)
        self.assertIn("Witch Hat", label)
        self.assertIn("12:00", label)

    def test_tab_cycle(self):
        self.assertEqual(next_airing_tab("today"), "tomorrow")
        self.assertEqual(next_airing_tab("tomorrow"), "week")
        self.assertEqual(previous_airing_tab("today"), "week")


if __name__ == "__main__":
    unittest.main()
