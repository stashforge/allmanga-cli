import types
import unittest

from allmanga_cli.playback import desktop


class FakeIpc:
    def __init__(self):
        self.loads = []
        self.props = {
            "percent-pos": 0,
            "playback-time": 0,
            "duration": 0,
        }

    def load(
            self, url, title, headers, referer, start_time=0, osd_msg="",
            audio_url="", subtitle_url=""):
        self.loads.append({
            "url": url,
            "title": title,
            "headers": headers,
            "referer": referer,
            "start_time": start_time,
            "osd_msg": osd_msg,
            "audio_url": audio_url,
            "subtitle_url": subtitle_url,
        })

    def wait_for_playback(
            self, stream_info, episode, total_eps, fetch_callback,
            is_binge=False):
        return "QUIT", 0


class DesktopPlaybackTests(unittest.TestCase):
    def test_dailymotion_split_av_uses_local_manifest_instead_of_audio_add(self):
        calls = []
        stopped = []
        original_start = desktop.start_local_content_server
        original_stop = desktop.stop_local_proxy
        try:
            desktop.start_local_content_server = (
                lambda content, filename, content_type: (
                    calls.append((content, filename, content_type))
                    or ("http://127.0.0.1:1234/stream.m3u8", types.SimpleNamespace())
                )
            )
            desktop.stop_local_proxy = lambda server: stopped.append(server)
            ipc = FakeIpc()
            stream = {
                "link": "https://vod.dmcdn.test/video/manifest.m3u8",
                "type": "hls",
                "resolution": "800p",
                "source_name": "Dailymotion",
                "referer": "",
                "headers": {},
                "audio_url": "https://vod.dmcdn.test/audio/manifest.m3u8",
                "dailymotion_video": "https://vod.dmcdn.test/video/manifest.m3u8",
                "dailymotion_audio": "https://vod.dmcdn.test/audio/manifest.m3u8",
            }

            result = desktop.play_desktop(
                ipc,
                "Test",
                "1",
                stream,
                get_resume_time=lambda *_args: 0,
                get_preferred_mirror=lambda *_args: {},
                update_stream_info=lambda _info: None,
            )
        finally:
            desktop.start_local_content_server = original_start
            desktop.stop_local_proxy = original_stop

        self.assertEqual(result[0], "QUIT")
        self.assertEqual(ipc.loads[0]["url"], "http://127.0.0.1:1234/stream.m3u8")
        self.assertEqual(ipc.loads[0]["audio_url"], "")
        self.assertEqual(calls[0][1], "stream.m3u8")
        self.assertEqual(calls[0][2], "application/vnd.apple.mpegurl")
        self.assertIn("EXT-X-MEDIA", calls[0][0])
        self.assertIn("https://vod.dmcdn.test/audio/manifest.m3u8", calls[0][0])
        self.assertEqual(len(stopped), 1)

    def test_non_dailymotion_external_audio_still_uses_audio_url(self):
        ipc = FakeIpc()
        stream = {
            "link": "https://cdn.example/video.m4s",
            "type": "dash",
            "resolution": "1080p",
            "source_name": "Ak",
            "referer": "",
            "headers": {},
            "audio_url": "https://cdn.example/audio.m4s",
        }

        desktop.play_desktop(
            ipc,
            "Test",
            "1",
            stream,
            get_resume_time=lambda *_args: 0,
            get_preferred_mirror=lambda *_args: {},
            update_stream_info=lambda _info: None,
        )

        self.assertEqual(ipc.loads[0]["url"], "https://cdn.example/video.m4s")
        self.assertEqual(ipc.loads[0]["audio_url"], "https://cdn.example/audio.m4s")


if __name__ == "__main__":
    unittest.main()
