import base64
import unittest

from allmanga_cli.providers import get_provider, provider_key
from allmanga_cli.providers.animexin import AnimeXinProvider
from allmanga_cli.providers.wordpress import (
    parse_mirrors,
    parse_series,
    parse_episode,
)


def encoded_iframe(src: str) -> str:
    return base64.b64encode(f'<iframe src="{src}"></iframe>'.encode()).decode()


class WordPressProviderTests(unittest.TestCase):
    def test_animexin_is_auto_discovered(self):
        self.assertEqual(provider_key("animexin"), "animexin")
        self.assertIsInstance(get_provider("animexin"), AnimeXinProvider)

    def test_animexin_ignores_registry_request_json_argument(self):
        provider = AnimeXinProvider(
            request_json_fn=lambda *_args, **_kwargs: self.fail("request_json should not be used"),
            fetch=lambda _url: '<div class="listupd"></div>',
            ajax_fetch=lambda _query: {},
        )

        self.assertEqual(provider.search("renegade"), [])

    def test_animexin_search_uses_ajax_json_and_normalizes_title_shape(self):
        provider = AnimeXinProvider(
            ajax_fetch=lambda _query: {
                "anime": [{
                    "all": [{
                        "ID": 19375,
                        "post_title": "Perfect World Movie: Ashes of Perfect Fire",
                        "post_link": "https://animexin.dev/perfect-world-movie-ashes-of-perfect-fire/",
                        "post_image": "https://animexin.dev/poster.jpg",
                        "post_genres": "Action, Adventure",
                        "post_type": "ONA",
                        "post_latest": "Part 3",
                        "post_sub": "Sub",
                    }],
                }],
            },
        )

        results = provider.search("perfect world")

        self.assertEqual(results[0]["name"], "Perfect World Movie: Ashes of Perfect Fire")
        self.assertEqual(results[0]["_provider"], "animexin")
        self.assertEqual(
            results[0]["_provider_id"],
            "https://animexin.dev/perfect-world-movie-ashes-of-perfect-fire/",
        )
        self.assertEqual(results[0]["thumbnail"], "https://animexin.dev/poster.jpg")
        self.assertEqual(results[0]["availableEpisodes"]["sub"], 3)
        self.assertEqual(results[0]["_provider_genres"], "Action, Adventure")

    def test_parse_mirrors_decodes_and_normalizes_embeds(self):
        page = f'''
        <select class="mirror">
          <option value="{encoded_iframe('https://geo.dailymotion.com/player/x.html?video=abc')}">Dailymotion</option>
          <option value="{encoded_iframe('https://play.d.tube?v=XJongYZtZ6LtCjsBx2JNWn')}">DTube</option>
        </select>
        '''

        mirrors = parse_mirrors("https://animexin.dev", page)

        self.assertEqual(mirrors[0].url, "https://www.dailymotion.com/video/abc")
        self.assertEqual(
            mirrors[1].url,
            "https://nas2.d.tube/videos/f56ea345-c383-4ec3-b7cd-5f81ba94114b/master.m3u8",
        )

    def test_parse_mirrors_prioritizes_english_then_neutral_then_other_languages(self):
        page = f'''
        <select class="mirror">
          <option value="{encoded_iframe('https://ok.ru/videoembed/1')}">Indonesia Ok</option>
          <option value="{encoded_iframe('https://www.dailymotion.com/embed/video/xabc')}">English Dailymotion</option>
          <option value="{encoded_iframe('https://rumble.com/embed/vabc/')}">All Rumble</option>
          <option value="{encoded_iframe('https://example.com/embed')}">Other</option>
        </select>
        '''

        mirrors = parse_mirrors("https://animexin.dev", page)

        self.assertEqual(
            [mirror.label for mirror in mirrors],
            ["English Dailymotion", "All Rumble", "Other", "Indonesia Ok"],
        )

    def test_parse_series_reads_episode_urls(self):
        page = '''
        <div class="eplister">
          <ul>
            <li><a href="https://animexin.dev/show-part-3/"><div class="epl-num">Part 3</div><div class="epl-title">Show Part 3</div></a></li>
            <li><a href="https://animexin.dev/show-episode-2/"><div class="epl-num">2</div><div class="epl-title">Show Episode 2</div></a></li>
          </ul>
        </div>
        '''

        episodes = parse_series("https://animexin.dev", page)

        self.assertEqual(
            [episode.url for episode in episodes],
            [
                "https://animexin.dev/show-part-3/",
                "https://animexin.dev/show-episode-2/",
            ],
        )
        self.assertEqual([episode.meta for episode in episodes], ["Part 3", "2"])

    def test_parse_episode_extracts_mirrors(self):
        page = f'''
        <h1 class="entry-title">Renegade Immortal Episode 142 Indonesia, English Sub</h1>
        Released on <span>May 24, 2026</span> · series <a href="https://animexin.dev/renegade-immortal/">Renegade Immortal</a>
        <option value="{encoded_iframe('https://odysee.com/%24/embed/%40Haiii%3Ab%2FAnimeXin.dev-renegade-ep-142%3Af?r=abc')}">Odysee</option>
        '''

        episode = parse_episode("https://animexin.dev", page)

        self.assertEqual(episode.title, "Renegade Immortal Episode 142 Indonesia, English Sub")
        self.assertEqual(episode.series_title, "Renegade Immortal")
        self.assertEqual(episode.mirrors[0].label, "Odysee")
        self.assertEqual(
            episode.mirrors[0].url,
            "https://odysee.com/@Haiii:b/AnimeXin.dev-renegade-ep-142:f",
        )

    def test_animexin_provider_returns_url_episode_ids_and_sources(self):
        pages = {
            "https://animexin.dev/?s=renegade": '''
                <div class="listupd">
                  <article><a href="https://animexin.dev/renegade-immortal/" title="Renegade Immortal"><h2>Renegade Immortal</h2></a></article>
                  <article><a href="https://animexin.dev/renegade-immortal-episode-1/" title="Renegade Immortal Episode 1"><h2>Renegade Immortal Episode 1</h2></a></article>
                </div>
            ''',
            "https://animexin.dev/renegade-immortal/": '''
                <div class="episodelist"><ul>
                  <li><a href="https://animexin.dev/renegade-immortal-episode-2/"><h3>Renegade Immortal Episode 2</h3></a></li>
                  <li><a href="https://animexin.dev/renegade-immortal-episode-1/"><h3>Renegade Immortal Episode 1</h3></a></li>
                </ul></div>
            ''',
            "https://animexin.dev/renegade-immortal-episode-1/": f'''
                <h1 class="entry-title">Renegade Immortal Episode 1</h1>
                <option value="{encoded_iframe('https://play.d.tube?v=XJongYZtZ6LtCjsBx2JNWn')}">DTube</option>
            ''',
        }
        provider = AnimeXinProvider(fetch=lambda url: pages[url])

        results = provider.search("renegade")
        catalog = provider.episode_catalog(results[0]["_provider_id"])
        sources = provider.episode_sources(
            results[0]["_provider_id"],
            catalog["ids"][0],
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["_provider"], "animexin")
        self.assertEqual(catalog["ids"][0], "https://animexin.dev/renegade-immortal-episode-1/")
        self.assertEqual(catalog["labels"][catalog["ids"][0]], "1")
        source = sources["episode"]["sourceUrls"][0]
        self.assertEqual(source["link"], "https://nas2.d.tube/videos/f56ea345-c383-4ec3-b7cd-5f81ba94114b/master.m3u8")
        self.assertNotIn("sourceUrl", source)
        self.assertEqual(source["_source_kind"], "direct")
        self.assertTrue(source["android_safe"])

    def test_animexin_provider_returns_embed_mirrors_as_unresolved_sources(self):
        pages = {
            "https://animexin.dev/renegade-immortal-episode-1/": f'''
                <h1 class="entry-title">Renegade Immortal Episode 1</h1>
                <option value="{encoded_iframe('https://www.dailymotion.com/embed/video/xabc')}">Dailymotion</option>
            ''',
        }
        provider = AnimeXinProvider(fetch=lambda url: pages[url])

        sources = provider.episode_sources(
            "https://animexin.dev/renegade-immortal/",
            "https://animexin.dev/renegade-immortal-episode-1/",
        )

        source = sources["episode"]["sourceUrls"][0]
        self.assertEqual(source["sourceUrl"], "https://www.dailymotion.com/video/xabc")
        self.assertNotIn("link", source)
        self.assertEqual(source["type"], "embed")
        self.assertEqual(source["_source_kind"], "embed")

    def test_animexin_provider_filters_indonesian_mirrors(self):
        pages = {
            "https://animexin.dev/renegade-immortal-episode-1/": f'''
                <h1 class="entry-title">Renegade Immortal Episode 1</h1>
                <option value="{encoded_iframe('https://rumble.com/embed/veng/')}">Hardsub English Rumble</option>
                <option value="{encoded_iframe('https://rumble.com/embed/vido/')}">Hardsub Indonesia Rumble</option>
                <option value="{encoded_iframe('https://ok.ru/videoembed/1')}">Indo Ok</option>
            ''',
        }
        provider = AnimeXinProvider(fetch=lambda url: pages[url])

        sources = provider.episode_sources(
            "https://animexin.dev/renegade-immortal/",
            "https://animexin.dev/renegade-immortal-episode-1/",
        )["episode"]["sourceUrls"]

        self.assertEqual(
            [source["sourceName"] for source in sources],
            ["Hardsub English Rumble"],
        )


if __name__ == "__main__":
    unittest.main()
