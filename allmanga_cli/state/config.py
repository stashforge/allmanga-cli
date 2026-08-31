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
    "sync": False,
    "cover": False,
    "download_dir": "",
    "anilist_sort": "recent",
    "anilist_sort_reverse": False,
    "spinner": "braille",
    "allanime_frontend_domain": "https://mkissa.to",
    "provider": "miruro",
    "aniskip": True,
    "auto_skip": True,
}

LEGACY_CONFIG_KEY_MAP = {
    "auto_track": "sync",
    "aniskip_enabled": "aniskip",
    "aniskip_auto": "auto_skip",
    "default_provider": "provider",
    "episode_order": "order",
}


def migrate_config_keys(config):
    """Migrate legacy configuration keys to canonical names in-place."""
    if not isinstance(config, dict):
        return False
    changed = False
    for old_key, new_key in LEGACY_CONFIG_KEY_MAP.items():
        if old_key in config:
            if new_key not in config:
                config[new_key] = config[old_key]
            del config[old_key]
            changed = True
    return changed


def secure_permissions(path):
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def secure_directory(path):
    try:
        os.chmod(path, 0o700)
    except Exception:
        pass


def save_config_file(path, config, disabled=False):
    if disabled:
        return False
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    secure_directory(directory)
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
            changed = migrate_config_keys(config)
            for key, value in defaults.items():
                if key not in config:
                    config[key] = value
                    changed = True
            if changed:
                save_config_file(path, config, disabled=disabled)
            return config
        except Exception as exc:
            if on_error:
                on_error(exc)
            if disabled:
                return defaults
            backup_path = f"{path}.bad-{int(time.time())}"
            try:
                os.replace(path, backup_path)
                secure_permissions(backup_path)
                if on_invalid:
                    on_invalid(backup_path)
            except Exception as move_error:
                if on_error:
                    on_error(move_error)
    save_config_file(path, defaults, disabled=disabled)
    return defaults

