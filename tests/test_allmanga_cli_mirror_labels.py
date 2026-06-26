import unittest

from allmanga_cli.app.playback import format_mirror_label


class MirrorLabelTests(unittest.TestCase):
    def test_label_skips_duplicate_type_and_resolution(self):
        label = format_mirror_label(
            {
                "source_name": "Hardsub English Rumble (1280x534)",
                "type": "hls",
                "resolution": "1280x534",
            },
            prefix="▶ ",
            safe_tag=" ✓",
        )

        self.assertEqual(label, "▶ Hardsub English Rumble (1280x534) [HLS ✓]")

    def test_label_skips_duplicate_hls_adaptive(self):
        label = format_mirror_label(
            {
                "source_name": "Hardsub English Rumble [HLS] Adaptive",
                "type": "hls",
                "resolution": "Adaptive",
            },
            safe_tag=" ✓",
        )

        self.assertEqual(label, "Hardsub English Rumble [HLS] Adaptive ✓")

    def test_label_keeps_type_and_resolution_when_name_is_plain(self):
        label = format_mirror_label(
            {
                "source_name": "Yt-MP4",
                "type": "mp4",
                "resolution": "1080p",
            },
            safe_tag=" ✓",
        )

        self.assertEqual(label, "Yt-MP4 [MP4 ✓] 1080p")


if __name__ == "__main__":
    unittest.main()
