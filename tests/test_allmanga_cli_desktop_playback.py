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
    def test_dailymotion_split_av_passes_audio_url_directly(self):
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

        self.assertEqual(result[0], "QUIT")
        self.assertEqual(ipc.loads[0]["url"], "https://vod.dmcdn.test/video/manifest.m3u8")
        self.assertEqual(ipc.loads[0]["audio_url"], "https://vod.dmcdn.test/audio/manifest.m3u8")

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

    def test_generic_hls_split_audio_passes_audio_url_directly(self):
        ipc = FakeIpc()
        stream = {
            "link": "https://cdn.example/video.m3u8",
            "type": "hls",
            "resolution": "1280x534",
            "source_name": "Rumble",
            "referer": "",
            "headers": {},
            "audio_url": "https://cdn.example/audio.m3u8",
        }

        desktop.play_desktop(
            ipc,
            "Test",
            "43",
            stream,
            get_resume_time=lambda *_args: 0,
            get_preferred_mirror=lambda *_args: {},
            update_stream_info=lambda _info: None,
        )

        self.assertEqual(ipc.loads[0]["url"], "https://cdn.example/video.m3u8")
        self.assertEqual(ipc.loads[0]["audio_url"], "https://cdn.example/audio.m3u8")
        self.assertEqual(ipc.loads[0]["title"], "Test - Episode 43 (1280x534)")


if __name__ == "__main__":
    unittest.main()
