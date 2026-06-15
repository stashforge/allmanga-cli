import unittest

from allmanga_cli.media.sources import expand_wixmp, source_priority


class SourcePriorityTests(unittest.TestCase):
    def test_known_working_mirrors_have_stable_order(self):
        sources = [
            {"sourceName": "Ok", "sourceUrl": "https://ok.example/embed"},
            {"sourceName": "Mp4", "sourceUrl": "https://mp4.example/embed"},
            {"sourceName": "Ak", "sourceUrl": "--encrypted"},
            {"sourceName": "Default", "sourceUrl": "--encrypted"},
            {
                "sourceName": "Yt-mp4",
                "sourceUrl": "https://tools.fast4speed.example/video",
            },
        ]

        ordered = sorted(sources, key=source_priority)

        self.assertEqual(
            [source["sourceName"] for source in ordered],
            ["Yt-mp4", "Default", "Ak", "Mp4", "Ok"],
        )

    def test_other_encrypted_mirrors_do_not_compete_with_default_or_ak(self):
        self.assertGreater(
            source_priority({"sourceName": "Other", "sourceUrl": "--value"}),
            source_priority({"sourceName": "Ak", "sourceUrl": "--value"}),
        )

    def test_wixmp_resolutions_are_best_first(self):
        streams = expand_wixmp(
            "https://repackager.wixmp.com/,480p,720p,1080p,/mp4/file.mp4"
        )

        self.assertEqual(list(streams), ["1080p", "720p", "480p"])


if __name__ == "__main__":
    unittest.main()
