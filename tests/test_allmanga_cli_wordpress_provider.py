import base64
import unittest

from allmanga_cli.providers import get_provider, provider_key
from allmanga_cli.providers.animekhor import AnimeKhorProvider
from allmanga_cli.providers.animexin import AnimeXinProvider
from allmanga_cli.providers.luciferdonghua import LuciferDonghuaProvider
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

    def test_lucifer_is_auto_discovered(self):
        self.assertEqual(provider_key("lucifer"), "lucifer")
        self.assertIsInstance(
            get_provider("lucifer"),
            LuciferDonghuaProvider,
        )

    def test_animekhor_is_auto_discovered(self):
        self.assertEqual(provider_key("animekhor"), "animekhor")
        self.assertIsInstance(get_provider("animekhor"), AnimeKhorProvider)

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
                        "post_image": "https://animexin.dev/poster.jpg?resize=214,300",
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

    def test_lucifer_reuses_wordpress_ajax_shape(self):
        provider = LuciferDonghuaProvider(
            ajax_fetch=lambda _query: {
                "anime": [{
                    "all": [{
                        "ID": 10,
                        "post_title": "Renegade Immortal",
                        "post_link": "https://luciferdonghua.in/renegade-immortal/",
                        "post_image": "https://luciferdonghua.in/poster.jpg",
                        "post_type": "ONA",
                        "post_latest": "142",
                        "post_sub": "Sub",
                    }],
                }],
            },
        )

        results = provider.search("renegade")

        self.assertEqual(results[0]["_provider"], "lucifer")
        self.assertEqual(results[0]["_provider_name"], "LuciferDonghua")
        self.assertEqual(
            results[0]["_provider_id"],
            "https://luciferdonghua.in/renegade-immortal/",
        )
        self.assertEqual(results[0]["availableEpisodes"]["sub"], 142)

    def test_animekhor_reuses_wordpress_ajax_shape(self):
        provider = AnimeKhorProvider(
            ajax_fetch=lambda _query: {
                "anime": [{
                    "all": [{
                        "ID": 11,
                        "post_title": "Soul Land",
                        "post_link": "https://animekhor.org/soul-land/",
                        "post_image": "https://animekhor.org/poster.jpg",
                        "post_type": "ONA",
                        "post_latest": "265",
                        "post_sub": "Sub",
                    }],
                }],
            },
        )

        results = provider.search("soul land")

        self.assertEqual(results[0]["_provider"], "animekhor")
        self.assertEqual(results[0]["_provider_name"], "AnimeKhor")
        self.assertEqual(results[0]["availableEpisodes"]["sub"], 265)

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

    def test_parse_mirrors_accepts_direct_option_urls(self):
        page = '''
        <select class="mirror">
          <option value="https://luciferdonghua.in/player/abc/">Hardsub English Dailymotion</option>
        </select>
        '''

        mirrors = parse_mirrors("https://luciferdonghua.in", page)

        self.assertEqual(len(mirrors), 1)
        self.assertEqual(mirrors[0].label, "Hardsub English Dailymotion")
        self.assertEqual(mirrors[0].url, "https://luciferdonghua.in/player/abc/")

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
                <option value="{encoded_iframe('https://www.dailymotion.com/embed/video/xmix')}">Indo + Eng Dailymotion</option>
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
            ["Hardsub English Rumble", "Indo + Eng Dailymotion"],
        )

    def test_lucifer_provider_resolves_internal_mirror_pages(self):
        pages = {
            "https://luciferdonghua.in/renegade-immortal-episode-1/": '''
                <h1 class="entry-title">Renegade Immortal Episode 1</h1>
                <option value="https://luciferdonghua.in/player/abc/">Hardsub English Dailymotion</option>
            ''',
            "https://luciferdonghua.in/player/abc/": '''
                <meta itemprop="embedUrl" content="https://geo.dailymotion.com/player/x.html?video=abc">
            ''',
        }
        provider = LuciferDonghuaProvider(fetch=lambda url: pages[url])

        sources = provider.episode_sources(
            "https://luciferdonghua.in/renegade-immortal/",
            "https://luciferdonghua.in/renegade-immortal-episode-1/",
        )["episode"]["sourceUrls"]

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["sourceUrl"], "https://www.dailymotion.com/video/abc")
        self.assertEqual(sources[0]["referer"], "https://luciferdonghua.in/player/abc/")

    def test_lucifer_provider_resolves_dailymotion_script_pages(self):
        pages = {
            "https://luciferdonghua.in/renegade-immortal-episode-1/": '''
                <h1 class="entry-title">Renegade Immortal Episode 1</h1>
                <option value="https://luciferdonghua.in/player/abc/">Hardsub English Dailymotion</option>
            ''',
            "https://luciferdonghua.in/player/abc/": '''
                <div class="player-embed">
                  <script src="https://geo.dailymotion.com/player/x.js" data-video="abc"></script>
                </div>
            ''',
        }
        provider = LuciferDonghuaProvider(fetch=lambda url: pages[url])

        sources = provider.episode_sources(
            "https://luciferdonghua.in/renegade-immortal/",
            "https://luciferdonghua.in/renegade-immortal-episode-1/",
        )["episode"]["sourceUrls"]

        self.assertEqual(sources[0]["sourceUrl"], "https://www.dailymotion.com/video/abc")


if __name__ == "__main__":
    unittest.main()
