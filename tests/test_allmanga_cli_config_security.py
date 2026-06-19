import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from allmanga_cli.state.config import load_config_file, save_config_file


class ConfigSecurityTests(unittest.TestCase):
    def test_config_directory_and_file_are_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config" / "config.json"

            save_config_file(str(config_path), {"anilist_token": "secret"})

            directory_mode = stat.S_IMODE(config_path.parent.stat().st_mode)
            file_mode = stat.S_IMODE(config_path.stat().st_mode)
            self.assertEqual(directory_mode, 0o700)
            self.assertEqual(file_mode, 0o600)

    def test_invalid_config_backup_remains_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config" / "config.json"
            config_path.parent.mkdir()
            config_path.write_text("{not json", encoding="utf-8")
            os.chmod(config_path, 0o644)

            load_config_file(str(config_path))

            backups = list(config_path.parent.glob("config.json.bad-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
            self.assertTrue(json.loads(config_path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
