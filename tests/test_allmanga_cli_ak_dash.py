import types
import unittest
import urllib.error
import urllib.request
from tests.app_namespace import load_app_namespace


def video(height, bandwidth, codec="avc1.640028"):
    return {
        "height": height,
        "width": height * 16 // 9,
        "bandwidth": bandwidth,
        "codecs": codec,
        "url": f"https://cdn.example/video-{height}-{bandwidth}.m4s?a=1&b=2",
        "segment_base": {"range": "0-9", "index_range": "10-19"},
    }


def audio(bandwidth):
    return {
        "bandwidth": bandwidth,
        "codecs": "mp4a.40.2",
        "url": f"https://cdn.example/audio-{bandwidth}.m4s?a=1&b=2",
        "segment_base": {"range": "0-7", "index_range": "8-15"},
    }


class AkDashResolverTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_app_namespace(reload=True)

    def test_prefers_avc_and_best_bitrate_per_resolution(self):
        item = {
            "rawUrls": {
                "duration": 120.5,
                "vids": [
                    video(1080, 900),
                    video(1080, 1400),
                    video(720, 500),
                    video(2160, 3000, "hev1.1.6.L150"),
                ],
                "audios": [audio(64), audio(192)],
            }
        }

        streams = self.ns["resolve_dash_raw_urls"](item, "Ak", 2)

        self.assertEqual(
            [stream["resolution"] for stream in streams],
            ["1080p", "720p"],
        )
        self.assertIn("video-1080-1400", streams[0]["link"])
        self.assertIn("audio-192", streams[0]["audio_url"])
        self.assertEqual(streams[0]["type"], "dash")
        self.assertFalse(streams[0]["android_safe"])

    def test_generated_mpd_contains_selected_video_and_audio(self):
        mpd = self.ns["generate_dash_mpd"](
            video(1080, 1400), audio(192), 120.5
        )

        self.assertIn('mimeType="video/mp4"', mpd)
        self.assertIn('mimeType="audio/mp4"', mpd)
        self.assertIn("video-1080-1400.m4s?a=1&amp;b=2", mpd)
        self.assertIn("audio-192.m4s?a=1&amp;b=2", mpd)
        self.assertIn('mediaPresentationDuration="PT120.500S"', mpd)

    def test_content_server_uses_dash_mime_and_secret_path(self):
        try:
            url, server = self.ns["start_local_content_server"](
                "<MPD/>", "stream.mpd", "application/dash+xml"
            )
        except PermissionError:
            self.skipTest("sandbox does not allow localhost sockets")
        self.addCleanup(self.ns["stop_local_proxy"], server)

        with urllib.request.urlopen(url, timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(
                response.headers.get_content_type(),
                "application/dash+xml",
            )
            self.assertEqual(response.read(), b"<MPD/>")
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(
                url.rsplit("/", 1)[0] + "/wrong.mpd", timeout=2
            )
        self.assertEqual(context.exception.code, 404)
        context.exception.close()


class AkDashPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_app_namespace(reload=True)

    def test_mpv_ipc_adds_external_audio_after_video(self):
        ipc = self.ns["MpvIpc"]()
        commands = []
        ipc.start = lambda: setattr(ipc, "running", True)
        ipc.send_cmd = lambda *args: commands.append(args)

        ipc.load(
            "https://cdn.example/video.m4s",
            "Test",
            {},
            "",
            audio_url="https://cdn.example/audio.m4s",
        )

        self.assertIn(
            ("loadfile", "https://cdn.example/video.m4s"), commands
        )
        self.assertIn(
            ("audio-add", "https://cdn.example/audio.m4s", "select"),
            commands,
        )
        self.assertLess(
            commands.index(("loadfile", "https://cdn.example/video.m4s")),
            commands.index(
                ("audio-add", "https://cdn.example/audio.m4s", "select")
            ),
        )

    def test_mpv_ipc_does_not_force_headers_for_plain_streams(self):
        ipc = self.ns["MpvIpc"]()
        commands = []
        ipc.start = lambda: setattr(ipc, "running", True)
        ipc.send_cmd = lambda *args: commands.append(args)

        ipc.load("https://cdn.example/video.m3u8", "Test", {}, "")

        self.assertNotIn(
            "http-header-fields",
            [command[1] for command in commands if command[:1] == ("set_property",)],
        )

    def test_mpv_ipc_passes_explicit_headers_and_referer(self):
        ipc = self.ns["MpvIpc"]()
        commands = []
        ipc.start = lambda: setattr(ipc, "running", True)
        ipc.send_cmd = lambda *args: commands.append(args)

        ipc.load(
            "https://cdn.example/video.m3u8",
            "Test",
            {"X-Test": "1"},
            "https://provider.example/watch",
        )

        self.assertIn(
            (
                "set_property",
                "http-header-fields",
                "X-Test: 1,Referer: https://provider.example/watch",
            ),
            commands,
        )

    def test_android_dash_launch_uses_local_mpd(self):
        play_android = self.ns["play_android"]
        globals_dict = play_android.__globals__
        server = types.SimpleNamespace(shutdown=lambda: None, server_close=lambda: None)
        commands = []
        original_content_server = globals_dict["start_local_content_server"]
        original_run = globals_dict["subprocess"].run
        try:
            globals_dict["start_local_content_server"] = (
                lambda *args, **kwargs: (
                    "http://127.0.0.1:1234/secret/stream.mpd",
                    server,
                )
            )
            globals_dict["subprocess"].run = lambda command, **kwargs: (
                commands.append(command) or types.SimpleNamespace(returncode=0)
            )
            stream = {
                "link": "https://cdn.example/video.m4s",
                "audio_url": "https://cdn.example/audio.m4s",
                "dash_video": video(1080, 1400),
                "dash_audio": audio(192),
                "dash_duration": 120.5,
                "headers": {},
                "referer": "",
            }

            self.assertTrue(
                play_android("Test", "1", stream, None, player="vlc")
            )
        finally:
            globals_dict["start_local_content_server"] = original_content_server
            globals_dict["subprocess"].run = original_run
            self.ns["cleanup_active_local_proxy"]()

        command = commands[0]
        self.assertIn("http://127.0.0.1:1234/secret/stream.mpd", command)
        self.assertIn("application/dash+xml", command)

    def test_dash_download_muxes_video_and_audio_with_ffmpeg(self):
        download = self.ns["download_episode"]
        globals_dict = download.__globals__
        commands = []
        original_which = globals_dict["shutil"].which
        original_run = globals_dict["subprocess"].run
        try:
            globals_dict["shutil"].which = lambda name: f"/usr/bin/{name}"
            globals_dict["subprocess"].run = lambda command, **kwargs: (
                commands.append(command) or types.SimpleNamespace(returncode=0)
            )
            stream = {
                "link": "https://cdn.example/video.m4s",
                "audio_url": "https://cdn.example/audio.m4s",
                "referer": "",
            }

            self.assertTrue(download("Test", "1", stream))
        finally:
            globals_dict["shutil"].which = original_which
            globals_dict["subprocess"].run = original_run

        command = commands[0]
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("https://cdn.example/video.m4s", command)
        self.assertIn("https://cdn.example/audio.m4s", command)
        self.assertIn("0:v:0", command)
        self.assertIn("1:a:0", command)


if __name__ == "__main__":
    unittest.main()
