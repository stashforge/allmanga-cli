"""Private runtime files used by mpv IPC sessions."""

import os
import shutil
import tempfile


TRANSITION_OSD_MS = 60 * 60 * 1000


def create_mpv_runtime():
    runtime_dir = tempfile.mkdtemp(prefix="allmanga-cli-")
    os.chmod(runtime_dir, 0o700)
    socket_path = os.path.join(runtime_dir, "mpv.sock")
    config_path = os.path.join(runtime_dir, "input.conf")
    descriptor = os.open(
        config_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as config:
        config.write("SHIFT+RIGHT script-message next_ep\n")
        config.write("SHIFT+LEFT script-message prev_ep\n")
    return runtime_dir, socket_path, config_path


def cleanup_mpv_runtime(runtime_dir):
    if runtime_dir:
        shutil.rmtree(runtime_dir, ignore_errors=True)
