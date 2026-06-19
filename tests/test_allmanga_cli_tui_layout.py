import unittest
from tests.app_namespace import load_app_namespace
from allmanga_cli.ui import picker
from allmanga_cli.ui import spinner
namespace = load_app_namespace()


class TuiLayoutTests(unittest.TestCase):
    def test_loading_frames_keep_original_braille_animation(self):
        original_time = spinner.time.time
        try:
            observed = []
            for timestamp in (0.0, 0.1, 0.2):
                spinner.time.time = lambda t=timestamp: t
                observed.append(namespace["_loading_frame"]())
        finally:
            spinner.time.time = original_time

        self.assertEqual(observed, ["⠋", "⠙", "⠹"])

    def test_spinner_supports_named_and_custom_frames(self):
        for preset in ("braille", "dots", "line", "pulse"):
            self.assertTrue(spinner.spinner_frames(preset))
        self.assertEqual(spinner.spinner_frame("line", now=0.0), "-")
        self.assertEqual(spinner.spinner_frame(["a", "b"], now=0.1), "b")
        self.assertEqual(spinner.spinner_from_config({"spinner": "dots"}), "dots")
        self.assertEqual(
            spinner.spinner_from_config({"ui": {"spinner": "pulse"}}),
            "pulse",
        )
        self.assertEqual(spinner.spinner_frames([]), spinner.spinner_frames("braille"))
        self.assertEqual(spinner.spinner_frames(["", "   "]), spinner.spinner_frames("braille"))
        self.assertEqual(spinner.spinner_frames(["", "  x "]), ["  x "])
        self.assertEqual(spinner.spinner_frames("unknown"), spinner.spinner_frames("braille"))
        self.assertEqual(
            {len(frame) for frame in spinner.spinner_frames("dots")},
            {4},
        )

    def test_poster_loading_tick_is_registered(self):
        self.assertIsNotNone(picker._poster_tick_fn)
        show = {"_poster_status": "loading"}
        namespace["_poster_needs_tick"].__globals__["SHOW_IMAGE"] = True

        self.assertTrue(picker._poster_needs_tick(show))

    def test_configured_loading_frame_uses_configured_spinner(self):
        original_style = namespace["_spinner_style"]
        original_time = spinner.time.time
        try:
            namespace["_configure_spinner_from_config"]({"spinner": "line"})
            spinner.time.time = lambda: 0.2
            self.assertEqual(namespace["_configured_loading_frame"](), "|")
        finally:
            namespace["_spinner_style"] = original_style
            spinner.time.time = original_time

    def test_cover_command_uses_high_quality_relative_output(self):
        command = namespace["_chafa_cover_command"]("/tmp/cover.jpg")

        self.assertNotIn("--format=symbols", command)
        self.assertIn("--relative=on", command)
        self.assertIn("--animate=off", command)
        self.assertIn(
            f"--size={namespace['POSTER_WIDTH']}x{namespace['POSTER_HEIGHT']}",
            command,
        )

    def test_native_cover_protocol_is_detected_and_not_split_into_rows(self):
        raw = "\033_Ga=T,c=12,r=8;payload\033\\"

        self.assertTrue(namespace["_poster_uses_native_protocol"](raw))
        self.assertEqual(namespace["_poster_symbol_lines"](raw, 8, 80), [])

    def test_symbol_fallback_is_clipped_to_reserved_height(self):
        raw = "\n".join(f"line {index}" for index in range(12))

        lines = namespace["_poster_symbol_lines"](raw, 8, 80)

        self.assertEqual(len(lines), 8)
        self.assertEqual(namespace["_strip_ansi"](lines[-1]), "line 7")

    def test_player_requests_poster_for_active_merged_show(self):
        get_player_poster = namespace["_get_player_poster"]
        original_get_poster = get_player_poster.__globals__["_get_poster"]
        requested = []
        show = {
            "_id": "provider-id",
            "_anilist_id": "123",
            "thumbnail": "https://img.test/anilist-cover.jpg",
        }
        try:
            get_player_poster.__globals__["_get_poster"] = (
                lambda current: requested.append(current) or "poster"
            )

            result = get_player_poster(show)
        finally:
            get_player_poster.__globals__["_get_poster"] = original_get_poster

        self.assertEqual(result, "poster")
        self.assertEqual(requested, [show])
        self.assertEqual(
            get_player_poster.__globals__["_hovered_show_id"],
            "provider-id",
        )

    def test_final_tui_line_cannot_reach_autowrap_column(self):
        line = "\033[1;97m" + ("界" * 20) + "\033[0m"
        fitted = namespace["_fit_terminal_line"](line, 20)

        self.assertLessEqual(namespace["_display_width"](fitted), 19)
        self.assertTrue(fitted.endswith("…"))

    def test_short_styled_line_is_unchanged(self):
        line = "\033[1;32mAIRING\033[0m"

        self.assertEqual(namespace["_fit_terminal_line"](line, 80), line)

    def test_absolute_frame_addresses_every_row_and_clears_it(self):
        frame = namespace["_absolute_terminal_frame"](
            ["first", "second"], rows=3, columns=20
        )

        self.assertIn("\033[1;1H\033[2Kfirst", frame)
        self.assertIn("\033[2;1H\033[2Ksecond", frame)
        self.assertTrue(frame.endswith("\033[3;1H\033[2K"))

    def test_picker_layout_exactly_fills_terminal_with_poster_gap(self):
        rows = 40
        header = 4
        poster = 8
        margin = 1
        gap = 0

        max_visible, shown, padding = namespace["_picker_vertical_layout"](
            rows, header, poster, margin, gap, item_count=40
        )

        self.assertEqual(shown, max_visible)
        self.assertEqual(
            padding + poster + margin + gap + shown + 1 + header,
            rows,
        )

    def test_short_info_panel_keeps_footer_on_bottom_row(self):
        align = namespace["_bottom_align_panel_lines"]

        self.assertEqual(
            align(["33 results  │  Enter/Right=open  Esc=back"], 4),
            ["", "", "", "33 results  │  Enter/Right=open  Esc=back"],
        )

    def test_full_info_panel_preserves_existing_rows(self):
        align = namespace["_bottom_align_panel_lines"]
        lines = ["title", "alternate", "metadata", "footer"]

        self.assertEqual(align(lines, 4), lines)

    def test_filtered_search_without_selection_keeps_four_header_rows(self):
        namespace["_search_result_header"].__globals__["_active_picker_query"] = "hehehe"
        header = namespace["_search_result_header"](
            "AllAnime",
            "one",
            "sub",
            lambda: [{"_id": "1", "name": "One Piece"}],
            lambda: "",
        )

        lines = header(-1).splitlines()

        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "")
        self.assertIn("No match: hehehe", namespace["_strip_ansi"](lines[1]))
        self.assertEqual(namespace["_strip_ansi"](lines[2]), "Source: AllAnime")
        self.assertIn('1 result(s) for "one"', namespace["_strip_ansi"](lines[3]))

    def test_loading_search_shows_history_hint_and_source(self):
        header = namespace["_search_result_header"](
            "AllAnime",
            "slime",
            "sub",
            lambda: [{"_id": "1", "name": "Partial result"}],
            lambda: "Searching...",
        )

        lines = header(0).splitlines()

        self.assertEqual(len(lines), 4)
        self.assertIn(
            "Use Up/Down to browse previous searches.",
            namespace["_strip_ansi"](lines[1]),
        )
        self.assertEqual(namespace["_strip_ansi"](lines[2]), "Source: AllAnime")
        self.assertEqual(namespace["_strip_ansi"](lines[3]), "Searching...")

    def test_anilist_menu_header_keeps_blank_info_row(self):
        lines = namespace["anilist_menu_header"]().splitlines()

        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "")
        self.assertEqual(
            namespace["_strip_ansi"](lines[1]),
            "Choose an AniList list.",
        )
        footer = namespace["_strip_ansi"](lines[3])
        self.assertIn("Left=search", footer)
        self.assertIn("Esc=quit", footer)

    def test_anilist_menu_distinguishes_left_from_escape(self):
        navigate = namespace["anilist_menu_navigation"]

        self.assertEqual(navigate(-2), "QUIT")
        self.assertEqual(navigate(-3), "SEARCH")
        self.assertIsNone(navigate(0))

    def test_direct_anilist_list_enters_alt_screen_before_loading(self):
        load_list = namespace["load_anilist_browse"]
        globals_dict = load_list.__globals__
        original_render = globals_dict["render_anilist_menu_loading"]
        original_loading = globals_dict["with_loading"]
        calls = []
        try:
            globals_dict["render_anilist_menu_loading"] = (
                lambda status: calls.append(("render", status))
            )

            def fake_loading(message, fn, *args):
                calls.append(("loading", message, args))
                return ["show"]

            globals_dict["with_loading"] = fake_loading
            result = load_list("token", "CURRENT")
        finally:
            globals_dict["render_anilist_menu_loading"] = original_render
            globals_dict["with_loading"] = original_loading

        self.assertEqual(result, ["show"])
        self.assertEqual(calls[0], ("render", "CURRENT"))
        self.assertEqual(calls[1][0], "loading")
        self.assertEqual(calls[1][1], "Loading AniList list: CURRENT")

    def test_direct_anilist_loading_frame_shows_menu_and_selection(self):
        frame = namespace["anilist_menu_loading_frame"]("CURRENT", 20, 80)
        plain = namespace["_strip_ansi"](frame)

        self.assertIn("AniList Lists ❯ 7/7", plain)
        self.assertIn("❯ Watching", plain)
        self.assertIn("Choose an AniList list.", plain)
        self.assertIn("Titles are matched to AllAnime before playback.", plain)


if __name__ == "__main__":
    unittest.main()
