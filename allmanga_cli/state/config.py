"""Configuration defaults and secure JSON persistence."""

import json
import os
import tempfile
import time


DEFAULT_CONFIG = {
    "quality": "1080p",
    "translation_type": "sub",
    "binge": False,
    "player": "mpv",
    "anilist_token": "",
    "auto_track": False,
    "cover": False,
    "download_dir": "",
    "anilist_sort": "recent",
}


def secure_permissions(path):
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def save_config_file(path, config, disabled=False):
    if disabled:
        return False
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".config.",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=4)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        secure_permissions(temp_path)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            os.remove(temp_path)
        except Exception:
            pass
        raise
    secure_permissions(path)
    return True


def load_config_file(
    path,
    *,
    disabled=False,
    on_error=None,
    on_invalid=None,
):
    defaults = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            if not disabled:
                secure_permissions(path)
            with open(path, encoding="utf-8") as handle:
                config = json.load(handle)
            for key, value in defaults.items():
                config.setdefault(key, value)
            return config
        except Exception as exc:
            if on_error:
                on_error(exc)
            if disabled:
                return defaults
            backup_path = f"{path}.bad-{int(time.time())}"
            try:
                os.replace(path, backup_path)
                if on_invalid:
                    on_invalid(backup_path)
            except Exception as move_error:
                if on_error:
                    on_error(move_error)
    save_config_file(path, defaults, disabled=disabled)
    return defaults
