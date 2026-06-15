import json
import unittest

from allmanga_cli.services import allanime


class AllAnimeEpisodeTests(unittest.TestCase):
    def test_episode_request_uses_youtu_chan_origin_and_referer(self):
        captured = {}

        def request_json(url, **kwargs):
            captured.update(kwargs)
            return {"data": {"tobeparsed": "encrypted"}}

        original_decrypt = allanime.decrypt_tobeparsed
        try:
            allanime.decrypt_tobeparsed = lambda value: json.dumps({
                "episode": {"sourceUrls": []},
            })
            result = allanime.get_episode_data(
                request_json,
                "show-id",
                "203",
                "sub",
            )
        finally:
            allanime.decrypt_tobeparsed = original_decrypt

        self.assertEqual(result, {"episode": {"sourceUrls": []}})
        self.assertEqual(
            captured["extra_hdrs"],
            {
                "Origin": "https://youtu-chan.com",
                "Referer": "https://youtu-chan.com",
            },
        )


if __name__ == "__main__":
    unittest.main()
