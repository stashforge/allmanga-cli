import os
import unittest

from allmanga_cli.ui.picker_render import get_key


class PickerKeyTests(unittest.TestCase):
    def read_key(self, data):
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, data)
            os.close(write_fd)
            write_fd = None
            return get_key(read_fd)
        finally:
            os.close(read_fd)
            if write_fd is not None:
                os.close(write_fd)

    def test_ctrl_shortcut_keys_are_decoded(self):
        self.assertEqual(self.read_key(b"\x04"), "CTRL_D")
        self.assertEqual(self.read_key(b"\x0e"), "CTRL_N")
        self.assertEqual(self.read_key(b"\x10"), "CTRL_P")


if __name__ == "__main__":
    unittest.main()
