import runpy
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"
communicate_with_cleanup = runpy.run_path(str(SCRIPT))["communicate_with_cleanup"]
read_bounded_process_stdout = runpy.run_path(str(SCRIPT))[
    "read_bounded_process_stdout"
]


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


if __name__ == "__main__":
    unittest.main()
