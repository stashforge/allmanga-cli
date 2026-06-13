import runpy
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"
namespace = runpy.run_path(str(SCRIPT))
fallback_tui_pick = namespace["fallback_tui_pick"]


class NonTtyFallbackTests(unittest.TestCase):
    def test_search_fallback_returns_typed_query(self):
        result = fallback_tui_pick(
            "Search Anime",
            [],
            return_query_on_enter=True,
            input_fn=lambda prompt: "slime",
            output_fn=lambda text: None,
        )

        self.assertEqual(result, "slime")

    def test_search_fallback_accepts_prefilled_query(self):
        result = fallback_tui_pick(
            "Match AllAnime",
            [],
            return_query_on_enter=True,
            initial_query="Boku dake ga Inai Machi",
            input_fn=lambda prompt: "",
            output_fn=lambda text: None,
        )

        self.assertEqual(result, "Boku dake ga Inai Machi")

    def test_search_fallback_eof_cancels(self):
        def eof(_prompt):
            raise EOFError

        self.assertEqual(
            fallback_tui_pick(
                "Search Anime",
                [],
                return_query_on_enter=True,
                input_fn=eof,
                output_fn=lambda text: None,
            ),
            -2,
        )

    def test_numbered_fallback_still_selects_options(self):
        answers = iter(["bad", "2"])

        result = fallback_tui_pick(
            "Choose",
            ["first", "second"],
            input_fn=lambda prompt: next(answers),
            output_fn=lambda text: None,
        )

        self.assertEqual(result, 1)

    def test_empty_non_search_fallback_cancels(self):
        messages = []

        result = fallback_tui_pick(
            "Choose",
            [],
            input_fn=lambda prompt: self.fail("input should not be requested"),
            output_fn=messages.append,
        )

        self.assertEqual(result, -2)
        self.assertIn("No selectable options.", messages)

    def test_tui_pick_uses_fallback_before_entering_alt_screen(self):
        tui_pick = namespace["tui_pick"]
        globals_dict = tui_pick.__globals__
        original_open = globals_dict["os"].open
        original_fallback = globals_dict["fallback_tui_pick"]
        original_enter = globals_dict["enter_alt_screen"]
        calls = []
        try:
            globals_dict["os"].open = (
                lambda *args, **kwargs: (_ for _ in ()).throw(OSError())
            )
            globals_dict["fallback_tui_pick"] = (
                lambda *args, **kwargs: calls.append(("fallback", kwargs)) or "query"
            )
            globals_dict["enter_alt_screen"] = lambda: calls.append(("alt", {}))

            result = tui_pick(
                "Search Anime",
                [],
                return_query_on_enter=True,
                initial_query="prefilled",
                is_search=True,
            )
        finally:
            globals_dict["os"].open = original_open
            globals_dict["fallback_tui_pick"] = original_fallback
            globals_dict["enter_alt_screen"] = original_enter

        self.assertEqual(result, "query")
        self.assertEqual(calls[0][0], "fallback")
        self.assertNotIn(("alt", {}), calls)
        self.assertTrue(calls[0][1]["return_query_on_enter"])
        self.assertEqual(calls[0][1]["initial_query"], "prefilled")


if __name__ == "__main__":
    unittest.main()
