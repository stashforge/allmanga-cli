import json
import unittest
import urllib.parse

from allmanga_cli.services import allanime
from allmanga_cli.core.api import ProviderVerificationRequired


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

    def test_episode_request_uses_compact_graphql_json(self):
        captured = {}

        def request_json(url, **kwargs):
            captured["url"] = url
            return {"data": {"episode": None}}

        result = allanime.get_episode_data(
            request_json,
            "show-id",
            "203",
            "sub",
        )

        self.assertIsNone(result)
        parsed = urllib.parse.urlsplit(captured["url"])
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(
            query["variables"][0],
            '{"showId":"show-id","translationType":"sub","episodeString":"203"}',
        )
        self.assertNotIn(": ", query["variables"][0])
        self.assertNotIn(", ", query["variables"][0])

    def test_episode_null_from_provider_does_not_crash(self):
        def request_json(url, **kwargs):
            return {"data": {"episode": None}}

        self.assertIsNone(allanime.get_episode_data(
            request_json,
            "show-id",
            "203",
            "sub",
        ))

    def test_episode_captcha_response_is_classified(self):
        def request_json(url, **kwargs):
            return {
                "errors": [{"message": "NEED_CAPTCHA"}],
                "data": {"episode": None},
            }

        with self.assertRaises(ProviderVerificationRequired):
            allanime.get_episode_data(
                request_json,
                "show-id",
                "203",
                "sub",
            )


if __name__ == "__main__":
    unittest.main()
