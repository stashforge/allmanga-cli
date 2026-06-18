import unittest
from tests.app_namespace import load_app_namespace
namespace = load_app_namespace()
sanitize_terminal_text = namespace["sanitize_terminal_text"]
get_show_display_title = namespace["get_show_display_title"]
render_item = namespace["_render_item"]


class TerminalTextTests(unittest.TestCase):
    def test_removes_csi_osc_and_control_characters(self):
        malicious = (
            "Safe\x1b[2J"
            "\x1b]52;c;clipboard\x07"
            "\x1bPpayload\x1b\\"
            "\nTitle\tHere\x00"
        )

        self.assertEqual(sanitize_terminal_text(malicious), "Safe Title Here")

    def test_display_title_is_sanitized(self):
        show = {"name": "Normal\x1b]0;fake title\x07\nSecond"}

        self.assertEqual(
            get_show_display_title(show),
            "Normal Second",
        )

    def test_list_renderer_preserves_only_application_styling(self):
        rendered = render_item("Anime\x1b[31mFAKE\x1b[0m\x1b]0;bad\x07", "", False)

        self.assertIn("AnimeFAKE", rendered)
        self.assertNotIn("bad", rendered)
        self.assertNotIn("\x1b[31m", rendered)
        self.assertTrue(rendered.startswith(namespace["_C_NORMAL"]))
        self.assertTrue(rendered.endswith(namespace["_RST"]))

    def test_plain_unicode_is_preserved(self):
        self.assertEqual(
            sanitize_terminal_text("Wu Shen Zhu Zai 日本語"),
            "Wu Shen Zhu Zai 日本語",
        )


if __name__ == "__main__":
    unittest.main()
