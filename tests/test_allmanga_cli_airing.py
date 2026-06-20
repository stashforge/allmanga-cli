import datetime as dt
import unittest
from pathlib import Path

from allmanga_cli.domain.airing import (
    airing_row_label,
    airing_rows,
    filter_airing_shows,
    next_airing_tab,
    previous_airing_tab,
)


APP_ANILIST = (
    Path(__file__).resolve().parents[1]
    / "allmanga_cli"
    / "app"
    / "anilist.py"
)
APP_CORE = (
    Path(__file__).resolve().parents[1]
    / "allmanga_cli"
    / "app_core.py"
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
            ["Later Show"],
        )

    def test_week_rows_group_days_without_selectable_headers(self):
        first = self.show("First", 50, 11)
        second = self.show("Second", 52, 12)
        later = self.show("Later", 74, 13)

        rows = airing_rows([later, second, first], "week", self.now)
        row_shows = [show for show, _label in rows]
        labels = [label for _show, label in rows]
        displayed = list(reversed(labels))

        self.assertIsNone(row_shows[2])
        self.assertIsNone(row_shows[4])
        self.assertIn("Monday", displayed[0])
        self.assertIn("EP 13", displayed[1])
        self.assertIn("Sunday", displayed[2])
        self.assertIn("EP 11", displayed[3])
        self.assertIn("EP 12", displayed[4])

    def test_today_row_uses_local_time_and_episode(self):
        label = airing_row_label(self.show("Witch Hat", 2, 11), tab="today", now=self.now)

        self.assertIn("EP 11", label)
        self.assertIn("Witch Hat", label)
        self.assertIn("12:00", label)

    def test_tab_cycle(self):
        self.assertEqual(next_airing_tab("today"), "tomorrow")
        self.assertEqual(next_airing_tab("tomorrow"), "week")
        self.assertEqual(previous_airing_tab("today"), "week")

    def test_refresh_stays_on_airing_screen(self):
        source = APP_ANILIST.read_text(encoding="utf-8")
        refresh_block = source.split("def _airing_refresh", 1)[1].split(
            "idx = tui_pick", 1
        )[0]

        self.assertIn("with_footer_loading", refresh_block)
        self.assertNotIn("_load_anilist_airing_shows", refresh_block)
        self.assertNotIn("with_anilist_menu_loading", refresh_block)

    def test_direct_airing_argument_is_consumed_after_initial_route(self):
        source = APP_CORE.read_text(encoding="utf-8")
        route_block = source.split('elif args.anilist == "airing":', 1)[1].split(
            "else:", 1
        )[0]

        self.assertIn('state = "ANILIST_AIRING"', route_block)
        self.assertIn('args.anilist = "menu"', route_block)

    def test_airing_uses_bottom_up_picker_layout(self):
        source = APP_ANILIST.read_text(encoding="utf-8")
        picker_block = source.split('lambda: f"AniList Airing', 1)[1].split(
            "help_dict=picker_help", 1
        )[0]

        self.assertNotIn("reverse_items=False", picker_block)


if __name__ == "__main__":
    unittest.main()
