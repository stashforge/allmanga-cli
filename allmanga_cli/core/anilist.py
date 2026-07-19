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


# ---------------------------------------------------------------------------
# Injected upper-layer hooks (wired by app_core; see storage.configure pattern)
# ---------------------------------------------------------------------------

_action_feedback_fn = None
_allanime_catalog_refresh_fn = None


def configure(*, action_feedback_fn=None, allanime_catalog_refresh_fn=None):
    """Inject the app-layer callbacks the sync/refresh paths need.

    * ``action_feedback_fn(show, msg)`` — post a toast on the show dict.
    * ``allanime_catalog_refresh_fn(entry)`` — refresh a history entry's
      provider episode catalog after an episode airs.
    """
    global _action_feedback_fn, _allanime_catalog_refresh_fn
    if action_feedback_fn is not None:
        _action_feedback_fn = action_feedback_fn
    if allanime_catalog_refresh_fn is not None:
        _allanime_catalog_refresh_fn = allanime_catalog_refresh_fn


def _feedback(show, msg):
    if _action_feedback_fn:
        _action_feedback_fn(show, msg)


# ---------------------------------------------------------------------------
# Sync orchestration
# ---------------------------------------------------------------------------

def should_update_anilist_progress(existing_progress, watched_episode):
    if watched_episode is None:
        return False

    from ..domain.episodes import anilist_progress_target_for_episode
    target_progress = anilist_progress_target_for_episode(watched_episode, fallback=None)

    if target_progress is None:
        return False

    if existing_progress is None:
        return True
    try:
        return target_progress > int(existing_progress)
    except (TypeError, ValueError):
        return True


def sync_progress_and_checkpoint(token, title, progress, media_id, show, ttype, status=None):
    from ..domain.tracking import (
        apply_tracking_progress_local,
        tracking_progress_for_sync,
        tracking_status_for_progress,
    )
    status = tracking_status_for_progress(show, progress) if status is None else status
    progress = tracking_progress_for_sync(show, progress, status)

    existing = show.get("_anilist_progress")
    prog_to_send = progress if should_update_anilist_progress(existing, progress) else None

    if not scrobble_anilist(
        token,
        title,
        prog_to_send,
        media_id=media_id,
        status=status,
        show=show,
    ):
        return False

    if progress is not None:
        apply_tracking_progress_local(show, progress, status)
    else:
        if status:
            show["_anilist_list"] = status
    show["_progress_authority"] = "AL"
    return True


def sync_watched_to_anilist(token, title, ep, media_id, show, ttype):
    return sync_progress_and_checkpoint(
        token, title, ep, media_id, show, ttype
    )


def save_and_sync_watched(show, episode, ttype, token, title, progress, media_id):
    storage.save_history(show, episode, ttype)

    if not (token and title and media_id):
        _feedback(show, f"Saved locally as EP {episode}.")
        return {"status": "local_saved"}

    from ..domain.episodes import anilist_progress_target_for_episode
    sync_prog = anilist_progress_target_for_episode(episode, fallback=progress)

    try:
        current_al = max(0, int(show.get("_anilist_progress") or 0))
    except (TypeError, ValueError):
        current_al = 0

    if sync_prog is None:
        # Fallback if invalid
        _feedback(show, f"Saved locally as EP {episode}.")
        return {"status": "local_saved"}

    if sync_prog <= current_al:
        _feedback(show, f"Saved locally as EP {episode}. AniList already ahead at EP {current_al}, sync skipped.")
        return {"status": "skipped", "anilist_target": sync_prog, "anilist_current": current_al}

    result = sync_watched_to_anilist(token, title, sync_prog, media_id, show, ttype)
    if result:
        _feedback(show, f"Saved locally as EP {episode}. AniList synced as EP {sync_prog}.")
        return {"status": "synced", "anilist_target": sync_prog}
    else:
        _feedback(show, f"Saved locally as EP {episode}. AniList sync failed.")
        return {"status": "failed"}


# ---------------------------------------------------------------------------
# Durable write-queue (mutations survive crashes; one worker thread drains)
# ---------------------------------------------------------------------------

import threading
import time as _time

from ..state import anilist_queue as anilist_queue_state
from ..state import paths as _paths
from ..services.http import ANILIST_TIMEOUT

_anilist_queue_lock = threading.RLock()
_anilist_queue_cache = None
_anilist_write_lock = threading.Lock()
_anilist_write_condition = threading.Condition(_anilist_write_lock)
_anilist_active_mutations = set()
_anilist_work_items = []
_anilist_worker = None


def _load_anilist_queue():
    global _anilist_queue_cache
    with _anilist_queue_lock:
        try:
            _anilist_queue_cache = anilist_queue_state.load_records(
                _paths.ANILIST_QUEUE_PATH,
                _anilist_queue_cache,
            )
        except Exception as e:
            debug_warn("Failed to load AniList mutation queue", e)
            storage._preserve_invalid_state_file(_paths.ANILIST_QUEUE_PATH, "AniList mutation queue")
            _anilist_queue_cache = []
        return _anilist_queue_cache


def _save_anilist_queue(records):
    global _anilist_queue_cache
    if _is_incognito():
        return False
    with _anilist_queue_lock:
        storage._atomic_write_json(_paths.ANILIST_QUEUE_PATH, records, indent=2)
        anilist_queue_state.secure_queue_file(_paths.ANILIST_QUEUE_PATH)
        _anilist_queue_cache = records
        return True


def _anilist_mutation_key(record):
    return anilist_queue_state.mutation_key(record)


def _enqueue_anilist_progress(media_id, title, progress, status, show, ttype,
                              pending_completion=None):
    date_updates = _anilist_date_updates(show or {}, progress, status)
    record = anilist_queue_state.make_progress_record(
        media_id,
        title,
        progress,
        status,
        show,
        ttype,
        pending_completion,
        date_updates=date_updates,
    )
    with _anilist_queue_lock:
        records = anilist_queue_state.replace_progress_record(
            _load_anilist_queue(),
            record,
        )
        _save_anilist_queue(records)
    return record


def _update_queued_mutation(mutation_id, **changes):
    with _anilist_queue_lock:
        records, changed = anilist_queue_state.update_record(
            _load_anilist_queue(),
            mutation_id,
            changes,
        )
        if changed:
            _save_anilist_queue(records)


def _remove_queued_mutation(mutation_id):
    with _anilist_queue_lock:
        _save_anilist_queue(anilist_queue_state.remove_record(
            _load_anilist_queue(),
            mutation_id,
        ))


def _checkpoint_queued_progress(record):
    return None


def _finish_queued_pending_completion(record):
    completion = record.get("pending_completion") or {}
    show_id = completion.get("show_id")
    episode = completion.get("episode")
    if not show_id or episode is None:
        return
    pending = storage.get_pending_completion(show_id)
    if str(pending.get("episode")) != str(episode):
        return
    storage.save_resume_time(show_id, episode, 0)
    storage.clear_pending_completion(show_id)


def _run_anilist_callback(callback, label):
    if not callback:
        return
    try:
        callback()
    except Exception as e:
        debug_warn(f"AniList {label} callback failed", e)


def _run_queued_anilist_progress(record, token, show=None,
                                  on_success=None, on_failure=None):
    from ..domain.tracking import apply_tracking_progress_local
    mutation_id = record["id"]
    success = False
    try:
        _update_queued_mutation(
            mutation_id,
            attempts=int(record.get("attempts") or 0) + 1,
            last_attempt_at=int(_time.time()),
        )
        prog_val = record.get("progress")
        prog_int = int(prog_val) if prog_val is not None else None
        success = scrobble_anilist(
            token,
            record.get("title") or "",
            prog_int,
            media_id=record.get("media_id"),
            status=record.get("status"),
            show=show,
            started_at=record.get("started_at"),
            completed_at=record.get("completed_at"),
        )
        if success:
            if show is not None:
                if prog_int is not None:
                    apply_tracking_progress_local(
                        show, prog_int, record.get("status")
                    )
                else:
                    if record.get("status"):
                        show["_anilist_list"] = record.get("status")
                show["_progress_authority"] = "AL"
            else:
                _checkpoint_queued_progress(record)
            _finish_queued_pending_completion(record)
            _remove_queued_mutation(mutation_id)
            _run_anilist_callback(on_success, "success")
        else:
            _update_queued_mutation(mutation_id, last_error="AniList update failed")
            _run_anilist_callback(on_failure, "failure")
    except Exception as e:
        debug_warn("Queued AniList update failed", e)
        _update_queued_mutation(mutation_id, last_error=str(e))
        _run_anilist_callback(on_failure, "failure")
    finally:
        with _anilist_write_condition:
            _anilist_active_mutations.discard(mutation_id)
            _anilist_write_condition.notify_all()
    return success


def _anilist_write_worker():
    global _anilist_worker
    while True:
        with _anilist_write_condition:
            if not _anilist_work_items:
                _anilist_worker = None
                _anilist_write_condition.notify_all()
                return
            record, token, show, on_success, on_failure = _anilist_work_items.pop(0)
        _run_queued_anilist_progress(
            record, token, show, on_success, on_failure
        )


def _start_queued_anilist_progress(record, token, show=None,
                                   on_success=None, on_failure=None):
    global _anilist_worker
    mutation_id = record.get("id")
    with _anilist_write_condition:
        if not mutation_id or mutation_id in _anilist_active_mutations:
            return None
        _anilist_active_mutations.add(mutation_id)
        _anilist_work_items.append(
            (record, token, show, on_success, on_failure)
        )
        if _anilist_worker is None:
            _anilist_worker = threading.Thread(
                target=_anilist_write_worker,
                name="anilist-write-worker",
                daemon=True,
            )
            _anilist_worker.start()
        _anilist_write_condition.notify_all()
        return record


def queue_anilist_progress(token, title, progress, media_id, show, ttype,
                           status=None, on_success=None, on_failure=None,
                           pending_completion=None):
    from ..domain.tracking import (
        tracking_progress_for_sync,
        tracking_status_for_progress,
    )
    if _is_incognito():
        return None
    status = tracking_status_for_progress(show, progress) if status is None else status
    progress = tracking_progress_for_sync(show, progress, status)

    existing = show.get("_anilist_progress") if show else None
    prog_to_send = progress if should_update_anilist_progress(existing, progress) else None

    try:
        record = _enqueue_anilist_progress(
            media_id, title, prog_to_send, status, show, ttype,
            pending_completion=pending_completion,
        )
    except Exception as e:
        debug_warn("Could not persist AniList update", e)
        if on_failure:
            on_failure()
        return None
    return _start_queued_anilist_progress(
        record, token, show, on_success, on_failure
    )


def retry_queued_anilist_writes(token):
    if _is_incognito():
        return 0
    if not token:
        return 0
    records = list(_load_anilist_queue())
    latest = {}
    for record in records:
        key = _anilist_mutation_key(record)
        previous = latest.get(key)
        if (previous and previous.get("pending_completion")
                and not record.get("pending_completion")):
            record["pending_completion"] = previous["pending_completion"]
        latest[key] = record
    records = sorted(
        latest.values(),
        key=lambda record: (int(record.get("created_at") or 0), record.get("id") or ""),
    )
    if len(records) != len(_load_anilist_queue()):
        _save_anilist_queue(records)
    started = 0
    for record in records:
        if _start_queued_anilist_progress(record, token):
            started += 1
    return started


def flush_anilist_writes(timeout=None):
    if _is_incognito():
        return True
    timeout = ANILIST_TIMEOUT + 2 if timeout is None else max(0, float(timeout))
    deadline = _time.monotonic() + timeout
    with _anilist_write_condition:
        while _anilist_active_mutations or _anilist_work_items:
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                return False
            _anilist_write_condition.wait(remaining)
        return True


# ---------------------------------------------------------------------------
# Progress reconciliation (local history vs AniList remote)
# ---------------------------------------------------------------------------

def _reconcile_status(show, progress):
    from ..domain import reconciliation as reconciliation_domain
    from ..domain.metadata import positive_int as _positive_int
    return reconciliation_domain.reconcile_status(
        show,
        progress,
        _positive_int,
    )


def _import_anilist_progress(show, ttype, progress, *, authority="AL"):
    progress = max(0, int(progress or 0))
    if progress > 0 or storage.get_history_entry(show, ttype):
        storage.write_history_progress(show, progress, ttype, last_synced=progress, touch=False)
    show["_anilist_progress"] = progress
    show["_local_progress"] = progress
    show["_progress_authority"] = authority
    show.pop("_sync_conflict", None)
    return {"action": "imported", "progress": progress}


def _push_local_progress(show, ttype, token, progress):
    from ..domain.tracking import apply_tracking_progress_local
    al_id = get_show_anilist_id(show)
    if not token or not al_id:
        return {"action": "failed", "progress": progress}
    status = _reconcile_status(show, progress)

    existing = show.get("_anilist_progress")
    prog_to_send = int(progress) if should_update_anilist_progress(existing, progress) else None

    if not update_anilist_entry(
        token,
        int(al_id),
        progress=prog_to_send,
        status=status,
        show=show,
    ):
        return {"action": "failed", "progress": progress}

    if progress is not None:
        apply_tracking_progress_local(show, int(progress), status)
    else:
        if status:
            show["_anilist_list"] = status

    show["_progress_authority"] = "AL"
    show.pop("_sync_conflict", None)
    return {"action": "pushed", "progress": int(progress) if progress is not None else None, "status": status}


def reconcile_progress(show, ttype, token, *, anilist_source=False, sync_enabled=True):
    from ..domain import reconciliation as reconciliation_domain
    local = storage.get_local_progress(show, ttype)
    local_label = storage.get_local_episode_label(show, ttype) or str(local if local is not None else 0)
    try:
        remote = max(0, int(show.get("_anilist_progress") or 0))
    except (TypeError, ValueError):
        remote = 0
    last = storage.get_last_synced_progress(show, ttype)
    show.pop("_sync_conflict", None)
    decision = reconciliation_domain.decide_progress_reconciliation(
        local=local,
        remote=remote,
        last_synced=last,
        status=show.get("_anilist_list"),
        anilist_source=anilist_source,
        sync_enabled=sync_enabled,
    )
    action = decision["action"]

    if action in ("import", "push"):
        conflict = {
            "local": local_label,
            "anilist": decision.get("anilist", remote),
        }
        show["_sync_conflict"] = conflict
        show["_progress_authority"] = decision.get("authority", "LOCAL")
        return {"action": "conflict", **conflict}

    if action == "local":
        show["_local_progress"] = local
        show["_progress_authority"] = decision["authority"]
        return {"action": "local", "progress": decision["progress"]}
    if action == "equal":
        storage.set_last_synced_progress(show, local, ttype)
        show["_progress_authority"] = "AL"
        return {"action": "equal", "progress": local}
    if action == "conflict":
        conflict = {
            "local": local_label,
            "anilist": decision["anilist"],
        }
        show["_sync_conflict"] = conflict
        show["_progress_authority"] = decision["authority"]
        return {"action": "conflict", **conflict}


# ---------------------------------------------------------------------------
# History refresh from AniList
# ---------------------------------------------------------------------------

def refresh_history_entry_from_anilist(entry, token):
    show = (entry or {}).get("show", {})
    media_id = get_anilist_media_id(show)
    if not token or not media_id or not show.get("_sync_enabled"):
        return False
    media = fetch_anilist_media(token, media_id)
    if not media:
        return False
    changed = update_anime_from_anilist_media(show, media)
    if changed and show.get("_anilist_progress") is not None:
        show["_progress_authority"] = "AL"
    return changed


def refresh_history_anilist_airing_batch(history_entries):
    now = int(_time.time())

    # 1 hour cooldown
    COOLDOWN = 3600

    media_ids_to_fetch = []
    entry_map = {}

    for entry in history_entries:
        show = entry.get("show")
        if not show:
            continue

        al_id = get_show_anilist_id(show)
        if not al_id:
            continue

        last_checked = show.get("_anilist_airing_checked_at", 0)
        next_airing_at = show.get("_next_airing_at")
        status = str(show.get("_anilist_status") or show.get("status") or "").upper()

        needs_refresh = False
        if next_airing_at and next_airing_at <= now:
            needs_refresh = True
        elif last_checked == 0:
            needs_refresh = True
        elif status in ("RELEASING", "NOT_YET_RELEASED", "UNKNOWN", "") and (now - last_checked) > COOLDOWN:
            needs_refresh = True

        if needs_refresh:
            media_ids_to_fetch.append(str(al_id))
            if str(al_id) not in entry_map:
                entry_map[str(al_id)] = []
            entry_map[str(al_id)].append({"entry": entry, "old_next_airing_at": next_airing_at})

    if not media_ids_to_fetch:
        return False

    # Deduplicate IDs
    media_ids_to_fetch = list(set(media_ids_to_fetch))

    try:
        batch_results = anilist_service.fetch_media_batch(anilist_urlopen, read_json_response, media_ids_to_fetch)
    except Exception as e:
        debug_warn("AniList batch fetch failed", e)
        return False

    changed = False
    for al_id, media in batch_results.items():
        items = entry_map.get(str(al_id), [])
        for item in items:
            entry = item["entry"]
            old_next_airing_at = item["old_next_airing_at"]
            show = entry.get("show")
            if not show: continue

            show["_anilist_airing_checked_at"] = now
            changed = True

            airing = media.get("nextAiringEpisode")
            if airing:
                new_ep = airing.get("episode")
                new_time = airing.get("timeUntilAiring")
                new_at = airing.get("airingAt")
                if not new_at and new_time:
                    new_at = now + new_time
                if new_ep != show.get("_next_airing_ep"):
                    show["_next_airing_ep"] = new_ep
                if new_at != show.get("_next_airing_at"):
                    show["_next_airing_at"] = new_at
                if new_time != show.get("_next_airing_time"):
                    show["_next_airing_time"] = new_time
            else:
                show.pop("_next_airing_ep", None)
                show.pop("_next_airing_time", None)
                show.pop("_next_airing_at", None)

            new_count = media.get("episodes")
            if new_count is not None and new_count != show.get("_anilist_episode_count"):
                show["_anilist_episode_count"] = new_count

            new_status = media.get("status")
            if new_status and show.get("_anilist_status") != new_status:
                show["_anilist_status"] = new_status
                changed = True

            if old_next_airing_at and old_next_airing_at <= now:
                if _allanime_catalog_refresh_fn and _allanime_catalog_refresh_fn(entry):
                    changed = True

    if changed:
        storage._atomic_write_json(_paths.HISTORY_PATH, storage.sanitize_history_list(history_entries), indent=2)
    return changed
