import runpy
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"
namespace = runpy.run_path(str(SCRIPT))


class ChildNavigationTests(unittest.TestCase):
    def test_multi_result_left_preserves_search_results(self):
        should_clear = namespace["should_clear_query_on_child_left"]

        self.assertFalse(should_clear("SEARCH", False))
        self.assertFalse(should_clear("ANILIST_SEARCH", False))

    def test_direct_single_left_opens_search_input(self):
        should_clear = namespace["should_clear_query_on_child_left"]

        self.assertTrue(should_clear("SEARCH", True))
        self.assertTrue(should_clear("ANILIST_SEARCH", True))


if __name__ == "__main__":
    unittest.main()
