import subprocess
import sys
import unittest
from unittest.mock import patch
from tests.app_namespace import load_app_namespace
namespace = load_app_namespace()
communicate_with_cleanup = namespace["communicate_with_cleanup"]
open_external_url = namespace["open_external_url"]
read_bounded_process_stdout = namespace["read_bounded_process_stdout"]


class FakeProcess:
    def __init__(self, communicate_results):
        self.communicate_results = iter(communicate_results)
        self.terminated = False
        self.killed = False
        self.calls = []

    def communicate(self, timeout=None):
        self.calls.append(timeout)
        result = next(self.communicate_results)
        if isinstance(result, Exception):
            raise result
        return result

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class ProcessCleanupTests(unittest.TestCase):
    def test_success_returns_output_without_stopping_process(self):
        process = FakeProcess([(b"out", b"err")])

        result = communicate_with_cleanup(process, timeout=20)

        self.assertEqual(result, (b"out", b"err"))
        self.assertFalse(process.terminated)
        self.assertFalse(process.killed)

    def test_timeout_terminates_and_reaps_process(self):
        process = FakeProcess([
            subprocess.TimeoutExpired("yt-dlp", 20),
            (b"", b""),
        ])

        with self.assertRaises(subprocess.TimeoutExpired):
            communicate_with_cleanup(process, timeout=20)

        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertEqual(process.calls, [20, 2])

    def test_stubborn_process_is_killed_and_reaped(self):
        process = FakeProcess([
            subprocess.TimeoutExpired("yt-dlp", 20),
            subprocess.TimeoutExpired("yt-dlp", 2),
            (b"", b""),
        ])

        with self.assertRaises(subprocess.TimeoutExpired):
            communicate_with_cleanup(process, timeout=20)

        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertEqual(process.calls, [20, 2, None])

    def test_bounded_reader_returns_small_stdout(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdout.write('small')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        output = read_bounded_process_stdout(process, timeout=2, max_bytes=16)

        self.assertEqual(output, b"small")
        self.assertEqual(process.returncode, 0)

    def test_bounded_reader_stops_oversized_stdout(self):
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys, time; sys.stdout.write('x' * 4096); "
                "sys.stdout.flush(); time.sleep(5)",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        with self.assertRaisesRegex(ValueError, "too large"):
            read_bounded_process_stdout(process, timeout=2, max_bytes=64)

        self.assertIsNotNone(process.returncode)

    def test_bounded_reader_preserves_timeout_cleanup(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        with self.assertRaises(subprocess.TimeoutExpired):
            read_bounded_process_stdout(
                process, timeout=0.05, max_bytes=64,
                shutdown_timeout=0.5,
            )

        self.assertIsNotNone(process.returncode)

    def test_termux_url_open_uses_termux_open_url_first(self):
        calls = []

        def fake_which(name):
            return "/bin/termux-open-url" if name == "termux-open-url" else None

        with patch.dict(open_external_url.__globals__, {"is_termux": lambda: True}):
            with patch.object(
                open_external_url.__globals__["shutil"],
                "which",
                side_effect=fake_which,
            ):
                with patch.object(
                    open_external_url.__globals__["subprocess"],
                    "Popen",
                    side_effect=lambda command, **kwargs: calls.append(command),
                ):
                    self.assertTrue(open_external_url("https://mkissa.to"))

        self.assertEqual(calls, [["/bin/termux-open-url", "https://mkissa.to"]])

    def test_termux_url_open_falls_back_to_android_intent(self):
        calls = []

        with patch.dict(open_external_url.__globals__, {"is_termux": lambda: True}):
            with patch.object(
                open_external_url.__globals__["shutil"],
                "which",
                return_value=None,
            ):
                with patch.object(
                    open_external_url.__globals__["subprocess"],
                    "Popen",
                    side_effect=lambda command, **kwargs: calls.append(command),
                ):
                    self.assertTrue(open_external_url("https://mkissa.to"))

        self.assertEqual(
            calls,
            [[
                "am",
                "start",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                "https://mkissa.to",
            ]],
        )


if __name__ == "__main__":
    unittest.main()
