"""AniList domain: auth/token storage, API calls, and list caches.

Owns every interaction with the AniList service that does not require the
provider/UI layers.  Sync orchestration and the write-queue worker live in
the app layer (they reach into provider catalogs and UI feedback); this
module is the network + credential + read-cache leader beneath them.

Dependencies point downward only:

    core.anilist -> services.anilist (GraphQL), services.http (urlopen)
    core.anilist -> state.secrets (OS keyring), core.storage (config)
    core.anilist -> core.reporting (debug_warn), context.FLAGS (incognito)

ANSI colour constants are declared locally, matching the existing
per-module convention (download.py, playback.py, …); there is no shared
colours module to depend on yet.
"""

import getpass

from ..context import FLAGS
from ..core import reporting
from ..core import storage
from ..core.api import (
    anilist_account_cache_key,
    read_json_response,
    search_failure_message,
)
from ..core.api import SearchFailure
from ..services import anilist as anilist_service
from ..services.http import anilist_urlopen
from ..state import secrets as secret_state

GREEN = "\033[1;32m"
RED = "\033[1;31m"
BOLD = "\033[1m"
RESET = "\033[0m"

debug_warn = reporting.debug_warn

# Read caches, invalidated on any successful write (update_anilist_entry).
_anilist_list_cache = {}
_anilist_search_cache = {}


def _is_incognito():
    return FLAGS.incognito_mode


# ---------------------------------------------------------------------------
# Token / auth
# ---------------------------------------------------------------------------

def save_anilist_token(cfg, token):
    token = storage.sanitize_token(token)
    if token and secret_state.set_secret(secret_state.ANILIST_KEY, token):
        disk_cfg = dict(cfg)
        disk_cfg["anilist_token"] = ""
        storage.save_config(disk_cfg)
        cfg["anilist_token"] = token
        return "secret"
    cfg["anilist_token"] = token or ""
    storage.save_config(cfg)
    return "config"


def clear_anilist_token(cfg):
    secret_state.delete_secret(secret_state.ANILIST_KEY)
    cfg["anilist_token"] = ""
    storage.save_config(cfg)


def anilist_token_storage_status(cfg):
    if secret_state.get_secret(secret_state.ANILIST_KEY):
        return "secret"
    if cfg.get("anilist_token"):
        return "config"
    return "none"


def mask_token(token):
    token = storage.sanitize_token(token)
    if not token:
        return ""
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}************{token[-4:]}"


def anilist_auth_status_lines(cfg):
    raw_secret_token = secret_state.get_secret(secret_state.ANILIST_KEY)
    raw_config_token = cfg.get("anilist_token") or ""
    secret_token = storage.sanitize_token(raw_secret_token)
    config_token = storage.sanitize_token(raw_config_token)
    store = "secret" if secret_token else ("config" if config_token else "none")
    token = secret_token or config_token
    keyring_path = secret_state.backend_path()
    lines = ["AniList"]
    if token:
        lines.append(f"  {GREEN}✓{RESET} Token stored")
    else:
        lines.append(f"  {RED}✗{RESET} Not logged in")
    if store == "secret":
        lines.append("  - Storage: OS secret storage")
    elif store == "config":
        lines.append("  - Storage: private config file")
    else:
        lines.append("  - Storage: none")
    from ..state import paths
    lines.append(f"  - Config: {paths.CONFIG_PATH}")
    if keyring_path:
        lines.append(f"  - Keyring: available ({keyring_path})")
    else:
        lines.append("  - Keyring: unavailable (secret-tool not found)")
    if token:
        lines.append(f"  - Token: {mask_token(token)}")
    if raw_secret_token != secret_token or raw_config_token != config_token:
        lines.append("  - Warning: token had wrapping quotes; they will be stripped on next login")
    if store == "config" and keyring_path:
        lines.append("  - Hint: run auth login again to move the token to keyring")
    return lines


def stored_anilist_token(cfg):
    return storage.sanitize_token(
        secret_state.get_secret(secret_state.ANILIST_KEY)
        or cfg.get("anilist_token")
        or ""
    )


def anilist_auth_login_existing_lines(cfg):
    return [
        "AniList",
        f"  {GREEN}✓{RESET} Already authenticated",
        "",
        "Run `auth logout` first to replace the stored token.",
    ]


def anilist_auth_token_lines(cfg, raw=False):
    token = stored_anilist_token(cfg)
    if not token:
        return None
    if raw:
        return [token]
    return [
        f"AniList token: {mask_token(token)}",
        "Use `auth token --raw` to reveal the complete token.",
    ]


def prompt_anilist_token():
    return storage.sanitize_token(getpass.getpass(f"\n{BOLD}Paste AniList Token: {RESET}"))


# ---------------------------------------------------------------------------
# Media / list / search API
# ---------------------------------------------------------------------------

def fetch_anilist_media(token, media_id):
    try:
        return anilist_service.fetch_media(
            anilist_urlopen,
            read_json_response,
            token,
            media_id,
        )
    except Exception as e:
        debug_warn("Failed to refresh AniList media", e)
        return {}


def get_show_anilist_id(show):
    try:
        if show.get("_anilist_id"):
            return int(show.get("_anilist_id"))
        if show.get("aniListId"):
            return int(show.get("aniListId"))
        match = show.get("anilistMatch")
        if isinstance(match, dict) and match.get("id"):
            return int(match["id"])
        return None
    except (ValueError, TypeError):
        return None


def get_show_mal_id(show):
    try:
        return int(show.get("malId")) if show.get("malId") else None
    except (ValueError, TypeError):
        return None


def get_anilist_media_id(anime):
    return get_show_anilist_id(anime)


def update_anime_from_anilist_media(anime, media):
    return anilist_service.apply_media_update(anime, media)


def fetch_anilist_list(token, status=None, force_refresh=False):
    cache_key = (
        anilist_account_cache_key(token),
        str(status or "ALL").upper(),
    )
    if not force_refresh and cache_key in _anilist_list_cache:
        return _anilist_list_cache[cache_key]

    try:
        shows = anilist_service.fetch_list(
            anilist_urlopen,
            read_json_response,
            token,
            status,
        )
        _anilist_list_cache[cache_key] = shows
        return shows
    except Exception as e:
        debug_warn("Failed to fetch AniList list", e)
        return []


def search_anilist(token, query, raise_errors=False):
    cache_key = (
        anilist_account_cache_key(token),
        str(query or "").strip().casefold(),
    )
    if cache_key in _anilist_search_cache:
        return _anilist_search_cache[cache_key]

    try:
        shows = anilist_service.search(
            anilist_urlopen,
            read_json_response,
            token,
            query,
        )
        _anilist_search_cache[cache_key] = shows
        return shows
    except SearchFailure as e:
        debug_warn("AniList search failed", e)
        if raise_errors:
            raise
        return []
    except Exception as e:
        debug_warn("AniList search failed", e)
        if raise_errors:
            raise SearchFailure(search_failure_message("AniList", e)) from e
        return []


# ---------------------------------------------------------------------------
# Entry writes (dates + mutation). Read caches invalidated on success.
# ---------------------------------------------------------------------------

def scrobble_anilist(
        token,
        title,
        ep,
        media_id=None,
        status=None,
        show=None,
        started_at=None,
        completed_at=None):
    try:
        if media_id is None:
            media_id = anilist_service.search_media_id(
                anilist_urlopen,
                read_json_response,
                title,
            )

        return update_anilist_entry(
            token,
            int(media_id),
            progress=ep,
            status=status,
            show=show,
            started_at=started_at,
            completed_at=completed_at,
        )
    except Exception:
        return False


def _fuzzy_date_has_value(value):
    return bool(
        isinstance(value, dict)
        and value.get("year")
        and value.get("month")
        and (value.get("day") or value.get("date"))
    )


def _today_fuzzy_date():
    from datetime import date
    today = date.today()
    return {
        "year": today.year,
        "month": today.month,
        "day": today.day,
    }


def _anilist_date_updates(show, progress=None, status=None):
    updates = {}
    normalized_status = str(status or "").upper()
    try:
        progress_value = int(progress) if progress is not None else None
    except (TypeError, ValueError):
        progress_value = None
    should_start = (
        (progress_value is not None and progress_value > 0)
        or normalized_status in {"CURRENT", "REPEATING", "COMPLETED"}
    )
    if should_start and not _fuzzy_date_has_value(show.get("_anilist_started_at")):
        updates["started_at"] = _today_fuzzy_date()
    if (
        normalized_status == "COMPLETED"
        and not _fuzzy_date_has_value(show.get("_anilist_completed_at"))
    ):
        updates["completed_at"] = _today_fuzzy_date()
    return updates


def update_anilist_entry(
        token,
        media_id,
        progress=None,
        status=None,
        score=None,
        show=None,
        started_at=None,
        completed_at=None):
    if _is_incognito():
        return False
    try:
        date_updates = _anilist_date_updates(show or {}, progress, status)
        if started_at is not None:
            date_updates["started_at"] = started_at
        if completed_at is not None:
            date_updates["completed_at"] = completed_at
        res = anilist_service.update_entry(
            anilist_urlopen,
            read_json_response,
            token,
            media_id,
            progress=progress,
            status=status,
            score=score,
            **date_updates,
        )
        if res.get("errors"):
            debug_warn("AniList update returned errors", res.get("errors"))
            return False
        entry = (res.get("data") or {}).get("SaveMediaListEntry") or {}
        if show is not None and entry:
            if entry.get("startedAt"):
                show["_anilist_started_at"] = entry["startedAt"]
            if entry.get("completedAt"):
                show["_anilist_completed_at"] = entry["completedAt"]
        _anilist_list_cache.clear()
        _anilist_search_cache.clear()
        return True
    except Exception as e:
        debug_warn("AniList update failed", e)
        return False
