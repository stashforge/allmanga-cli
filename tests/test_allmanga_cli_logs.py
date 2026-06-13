import os
import runpy
import stat
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "allmanga-cli"
namespace = runpy.run_path(str(SCRIPT))
write_private_log = namespace["write_private_log"]


class PrivateLogTests(unittest.TestCase):
    def test_log_uses_private_directory_and_file_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "state" / "logs"
            write_private_log.__globals__["LOG_DIR"] = str(log_dir)

            path = Path(write_private_log("crash.log", "private traceback"))

            self.assertEqual(path, log_dir / "crash.log")
            self.assertEqual(path.read_text(), "private traceback\n")
            self.assertEqual(stat.S_IMODE(log_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_log_filename_cannot_escape_private_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            write_private_log.__globals__["LOG_DIR"] = str(log_dir)

            path = Path(write_private_log("../../outside.log", "traceback"))

            self.assertEqual(path, log_dir / "outside.log")
            self.assertFalse((Path(temp_dir) / "outside.log").exists())


if __name__ == "__main__":
    unittest.main()
