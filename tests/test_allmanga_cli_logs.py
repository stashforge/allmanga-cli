import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.app_namespace import load_app_namespace
from allmanga_cli.context import FLAGS
from allmanga_cli.state import paths
namespace = load_app_namespace()
write_private_log = namespace["write_private_log"]


class PrivateLogTests(unittest.TestCase):
    def setUp(self):
        self._orig_flags = (FLAGS.incognito_mode, FLAGS.debug_mode)
        FLAGS.incognito_mode = False
        FLAGS.debug_mode = True
        self.addCleanup(self._restore_flags)

    def _restore_flags(self):
        FLAGS.incognito_mode, FLAGS.debug_mode = self._orig_flags

    def test_log_uses_private_directory_and_file_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "state" / "logs"
            with patch.object(paths, "LOG_DIR", str(log_dir)):
                path = Path(write_private_log("crash.log", "private traceback"))

            self.assertEqual(path, log_dir / "crash.log")
            self.assertEqual(path.read_text(), "private traceback\n")
            self.assertEqual(stat.S_IMODE(log_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_log_filename_cannot_escape_private_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            with patch.object(paths, "LOG_DIR", str(log_dir)):
                path = Path(write_private_log("../../outside.log", "traceback"))

            self.assertEqual(path, log_dir / "outside.log")
            self.assertFalse((Path(temp_dir) / "outside.log").exists())

    def test_private_log_redacts_tokens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            jwt = "eyJ" + "a" * 30 + "." + "b" * 12 + "." + "c" * 12

            with patch.object(paths, "LOG_DIR", str(log_dir)):
                path = Path(write_private_log("crash.log", f"Authorization: Bearer abc\n{jwt}"))
            text = path.read_text()

            self.assertIn("Authorization: Bearer <redacted>", text)
            self.assertIn("<redacted-jwt>", text)
            self.assertNotIn(jwt, text)


if __name__ == "__main__":
    unittest.main()
