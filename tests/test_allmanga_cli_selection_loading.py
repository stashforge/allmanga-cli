import unittest
from tests.app_namespace import load_app_namespace


class SelectionLoadingTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_app_namespace(reload=True)
        self.load_ids = self.ns["load_episode_ids_for_selection"]
        self.globals = self.load_ids.__globals__
        self.original_loading = self.globals["with_loading"]
        self.original_ensure = self.globals["ensure_episode_ids"]

    def tearDown(self):
        self.globals["with_loading"] = self.original_loading
        self.globals["ensure_episode_ids"] = self.original_ensure

    def test_uncached_catalog_shows_loading_feedback(self):
        calls = []
        show = {"_id": "show-1"}
        self.globals["ensure_episode_ids"] = lambda value, ttype: ["1", "2"]

        def fake_loading(message, function, *args):
            calls.append((message, function, args))
            return function(*args)

        self.globals["with_loading"] = fake_loading

        self.assertEqual(self.load_ids(show, "sub"), ["1", "2"])
        self.assertEqual(calls[0][0], "Loading episode list...")

    def test_loaded_catalog_skips_loading_feedback(self):
        calls = []
        show = {
            "_id": "show-1",
            "_episode_ids_ttype": "sub",
            "_episode_ids": ["1", "2"],
            "_episode_catalog_state": "loaded",
        }
        self.globals["with_loading"] = lambda *args, **kwargs: calls.append(args)
        self.globals["ensure_episode_ids"] = lambda value, ttype: ["1", "2"]

        self.assertEqual(self.load_ids(show, "sub"), ["1", "2"])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
