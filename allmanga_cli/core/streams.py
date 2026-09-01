"""Stream resolution: source ordering, foreground pick, background fill.

Owns the shared stream pool for the current episode and the background
worker that resolves the remaining mirrors after the first one is playing.
Generation counters invalidate workers left over from a previous episode.

Dependencies point downward only:

    core.streams -> media.resolver (resolve_source, generate_source_passes)
    core.streams -> media.sources (source_priority)
    core.streams -> core.storage (get_preferred_mirror)

One upper-layer fact is injected via :func:`configure`:
``episode_data_fn(show_id, ep, ttype, provider_id)`` — the provider episode
catalog lookup (``get_episode_data`` in app_core), which pulls in
provider/UI wiring that must not be imported downward.

``resolve_source`` is bound at import from media.resolver but kept as a
module global so tests can patch ``streams.resolve_source`` (or via the
``__globals__`` of any moved function) exactly as before.
"""

import time
import threading
from typing import Optional

from . import reporting
from ..media.resolver import resolve_source
from ..media.sources import source_priority, is_stream_valid, is_stream_valid_fast, calculate_stream_expiry, check_stream_health_and_refresh
from .storage import get_preferred_mirror

YELLOW = "\033[1;33m"
RESET = "\033[0m"

_episode_data_fn = None


def is_fixed_resolution(src: dict) -> bool:
    res = str(src.get("resolution") or "").strip().lower()
    name = str(src.get("sourceName") or "").strip().lower()
    if res and res not in ("auto", "adaptive", "?"):
        return True
    import re
    if re.search(r'\b(1080p?|720p?|480p?|360p?|\d+x\d+)\b', name):
        return True
    return False


def expand_direct_sources(sources: list) -> list:
    """
    If a source provides a direct auto/adaptive stream without parsed variants,
    allow a background yt-dlp worker to extract individual qualities (720p, 1080p).
    Never duplicate fixed-resolution streams (e.g. 1080p, 720p, 480p) or sources
    that already have individual variants provided.
    """
    has_variants = set()
    for src in sources:
        sname = str(src.get("sourceName") or "")
        base_name = sname.split(" (")[0].strip()
        if is_fixed_resolution(src):
            has_variants.add(base_name)

    expanded = []
    for src in sources:
        expanded.append(src)
        url = src.get("link") or src.get("streamUrl")
        sname = str(src.get("sourceName") or "")
        base_name = sname.split(" (")[0].strip()

        if is_fixed_resolution(src) or base_name in has_variants:
            continue

        if url and ("Yt-Dlp" not in sname and "yt-dlp" not in sname.lower()):
            ytdl_src = src.copy()
            ytdl_src.pop("link", None)
            ytdl_src.pop("streamUrl", None)
            ytdl_src["sourceUrl"] = url
            ytdl_src["sourceName"] = f"{base_name} Yt-Dlp"
            expanded.append(ytdl_src)
    return expanded


def configure(*, episode_data_fn=None):
    """Inject the provider episode-catalog lookup (see module docstring)."""
    global _episode_data_fn
    if episode_data_fn is not None:
        _episode_data_fn = episode_data_fn


# Keyed stream cache: (show_id, ep_id, ttype, provider_id) -> dict
_streams_cache: dict[tuple, dict] = {}
_active_stream_key: tuple | None = None

# all_streams is kept for backwards compatibility and references the active episode's streams.
all_streams: list = []
_streams_lock = threading.RLock()  # reentrant lock guards all_streams and _streams_cache
_streams_generation = 0  # invalidates workers started for an older episode
_bg_thread = None  # type: Optional[threading.Thread]
_bg_lock = threading.RLock()  # reentrant lock guards _bg_thread and _bg_stats
_bg_generation = 0
_bg_stats = {"resolved": 0, "failed": 0, "total": 0, "current": ""}


def make_stream_key(show_id=None, ep=None, ttype="sub", provider_id=None) -> tuple:
    return (
        str(show_id or ""),
        str(ep or ""),
        str(ttype or "sub").lower(),
        str(provider_id or "").lower(),
    )


def _clear_streams(key=None):
    global _streams_generation, _active_stream_key
    with _streams_lock:
        _streams_generation += 1
        all_streams.clear()
        if key is not None:
            k = key if isinstance(key, tuple) else make_stream_key(key)
            _streams_cache.pop(k, None)
        else:
            _active_stream_key = None
        return _streams_generation


def _extend_streams(streams, key=None):
    now = time.time()
    for s in streams:
        if isinstance(s, dict):
            s.setdefault("resolved_at", now)
            if "expires_at" not in s:
                s["expires_at"] = calculate_stream_expiry(s, s["resolved_at"])
    with _streams_lock:
        all_streams.extend(streams)
        if key is not None:
            k = key if isinstance(key, tuple) else make_stream_key(key)
            if k not in _streams_cache:
                _streams_cache[k] = {"streams": [], "resolved_at": now, "ep_data": None}
            _streams_cache[k]["streams"].extend(streams)


def _stream_snapshot(show_id=None, ep=None, ttype="sub", provider_id=None) -> list:
    now = time.time()
    with _streams_lock:
        if show_id is not None:
            k = make_stream_key(show_id, ep, ttype, provider_id)
            entry = _streams_cache.get(k)
            if not entry:
                return []
            valid = [s for s in entry.get("streams", []) if is_stream_valid_fast(s, now)]
            entry["streams"] = valid
            return list(valid)
        elif _active_stream_key is not None:
            entry = _streams_cache.get(_active_stream_key)
            if entry:
                valid = [s for s in entry.get("streams", []) if is_stream_valid_fast(s, now)]
                entry["streams"] = valid
                return list(valid)
        valid_all = [s for s in all_streams if is_stream_valid_fast(s, now)]
        all_streams[:] = valid_all
        return list(valid_all)


def _prune_dead_stream(key, stream_link: str):
    """Remove a dead/failing stream from cache."""
    if not stream_link:
        return
    with _streams_lock:
        k = key if isinstance(key, tuple) else make_stream_key(key)
        entry = _streams_cache.get(k)
        if entry and "streams" in entry:
            entry["streams"] = [s for s in entry["streams"] if (s.get("link") != stream_link and s.get("streamUrl") != stream_link)]


def _stream_count(show_id=None, ep=None, ttype="sub", provider_id=None) -> int:
    return len(_stream_snapshot(show_id, ep, ttype, provider_id))


def _get_cached_ep_data(key=None, show_id=None, ep=None, ttype="sub", provider_id=None) -> dict | None:
    with _streams_lock:
        if key is not None:
            k = key if isinstance(key, tuple) else make_stream_key(key)
        elif show_id is not None:
            k = make_stream_key(show_id, ep, ttype, provider_id)
        elif _active_stream_key is not None:
            k = _active_stream_key
        else:
            return None
        entry = _streams_cache.get(k)
        return entry.get("ep_data") if entry else None


def _set_cached_ep_data(ep_data: dict, key=None, show_id=None, ep=None, ttype="sub", provider_id=None):
    if not ep_data:
        return
    now = time.time()
    with _streams_lock:
        if key is not None:
            k = key if isinstance(key, tuple) else make_stream_key(key)
        elif show_id is not None:
            k = make_stream_key(show_id, ep, ttype, provider_id)
        else:
            return
        if k not in _streams_cache:
            _streams_cache[k] = {"state": "READY", "streams": [], "resolved_at": now, "ep_data": ep_data}
        else:
            _streams_cache[k]["ep_data"] = ep_data
def _publish_stream(stream, generation, key=None):
    """Publish a resolved stream only while its episode generation is current."""
    now = time.time()
    stream.setdefault("created_at", now)
    stream.setdefault("validated_at", now)
    if "expires_at" not in stream:
        stream["expires_at"] = calculate_stream_expiry(stream, stream["created_at"])
    sname = stream.get("source_name")
    res = stream.get("resolution")

    with _streams_lock:
        if generation != _streams_generation:
            return False

        # Fresh Stream Replacement / Upsert in all_streams
        found_idx = next(
            (i for i, existing in enumerate(all_streams)
             if existing.get("source_name") == sname and existing.get("resolution") == res),
            None
        )
        if found_idx is not None:
            all_streams[found_idx] = stream
        else:
            all_streams.append(stream)

        if key is not None:
            k = key if isinstance(key, tuple) else make_stream_key(key)
            if k not in _streams_cache:
                _streams_cache[k] = {"state": "READY", "streams": [], "resolved_at": now, "ep_data": None}
            entry = _streams_cache[k]
            cache_streams = entry.get("streams", [])
            c_found_idx = next(
                (i for i, existing in enumerate(cache_streams)
                 if existing.get("source_name") == sname and existing.get("resolution") == res),
                None
            )
            if c_found_idx is not None:
                cache_streams[c_found_idx] = stream
            else:
                cache_streams.append(stream)
            entry["streams"] = cache_streams
            entry["state"] = "READY"
        return True


def _generation_is_current(generation):
    with _streams_lock:
        return generation == _streams_generation


def _update_bg_stats(generation, *, current=None, resolved=0, failed=0, status_msg=None):
    with _bg_lock:
        if generation != _bg_generation:
            return False
        if current is not None:
            _bg_stats["current"] = current
        if status_msg is not None:
            _bg_stats["status_msg"] = status_msg
        _bg_stats["resolved"] += resolved
        _bg_stats["failed"] += failed
        return True


def start_bg_resolve(
    ep_data,
    exclude_names: set,
    show_id=None,
    ep=None,
    ttype="sub",
    provider_id=None
):
    """
    Start resolving all remaining sources in background for a specific show/ep.
    exclude_names: source names already resolved (skip them to avoid duplicates).
    """
    global _streams_generation, _bg_thread, _bg_generation, _bg_stats, _active_stream_key
    sources = ep_data.get("episode", {}).get("sourceUrls", []) if ep_data else []
    sources = expand_direct_sources(sources)
    sources = sorted(sources, key=source_priority)
    now = time.time()
    
    stream_key = make_stream_key(show_id, ep, ttype, provider_id) if show_id is not None else None

    with _streams_lock:
        _streams_generation += 1
        generation = _streams_generation
        _active_stream_key = stream_key
        all_streams.clear()
        if stream_key is not None:
            if stream_key not in _streams_cache:
                _streams_cache[stream_key] = {"state": "RESOLVING", "streams": [], "resolved_at": now, "ep_data": ep_data}
            else:
                curr_state = _streams_cache[stream_key].get("state", "READY")
                _streams_cache[stream_key]["state"] = "REFRESHING" if curr_state in ("READY", "STALE") else "RESOLVING"
                if ep_data:
                    _streams_cache[stream_key]["ep_data"] = ep_data
            # Populate all_streams with still-valid existing cached streams
            existing_valid = [s for s in _streams_cache[stream_key].get("streams", []) if is_stream_valid(s, now)]
            _streams_cache[stream_key]["streams"] = existing_valid
            all_streams.extend(existing_valid)
        seen_keys = {(s.get("source_name"), s.get("resolution")) for s in all_streams}

    with _bg_lock:
        _bg_generation = generation
        _bg_stats = {
            "resolved": len(exclude_names),
            "failed": 0,
            "total": len(sources),
            "current": "",
            "status_msg": "checking sources..." if sources else "Loading sources…",
        }

    def worker():
        nonlocal sources
        if not sources and _episode_data_fn and show_id:
            try:
                fetched_ep_data = _episode_data_fn(show_id, ep, ttype, provider_id=provider_id)
                if not _generation_is_current(generation):
                    return
                if fetched_ep_data:
                    _set_cached_ep_data(fetched_ep_data, key=stream_key)
                    raw_sources = fetched_ep_data.get("episode", {}).get("sourceUrls", [])
                    sources = expand_direct_sources(raw_sources)
                    sources = sorted(sources, key=source_priority)
                    with _bg_lock:
                        if _bg_generation == generation:
                            _bg_stats["total"] = len(sources)
            except Exception:
                pass

        from ..media.resolver import generate_source_passes
        for src, failed_queue, is_retry, is_final_pass in generate_source_passes(sources, max_passes=3):
            if not _generation_is_current(generation):
                return
            sname = src.get("sourceName", "")
            if not sname:
                continue
            clean_sname = sname.title()
            if sname in exclude_names or clean_sname in exclude_names or any(sname.lower() in ex.lower() for ex in exclude_names):
                continue
            
            display_name = sname
            if not _update_bg_stats(generation, current=display_name, status_msg=f"checking {display_name.lower()}..."):
                return
            try:
                found = False
                for stream in resolve_source(src, silent=True):
                    if not _generation_is_current(generation):
                        return
                    s_key = (stream.get("source_name"), stream.get("resolution"))
                    if s_key not in seen_keys and _publish_stream(stream, generation, key=stream_key):
                        seen_keys.add(s_key)
                        found = True
                        
                if not found:
                    if not is_final_pass:
                        failed_queue.append(src)
                
                inc_failed = 1 if not found and is_final_pass else 0
                inc_resolved = 1 if found else 0
                
                status_msg = f"checking {display_name.lower()}..." if found else f"{display_name} unavailable"
                if inc_resolved or inc_failed:
                    if not _update_bg_stats(
                        generation,
                        resolved=inc_resolved,
                        failed=inc_failed,
                        status_msg=status_msg,
                    ):
                        return
            except Exception:
                if not is_final_pass:
                    failed_queue.append(src)
                else:
                    if not _update_bg_stats(generation, failed=1, status_msg=f"{display_name} unavailable"):
                        return
        
        with _streams_lock:
            if generation == _streams_generation and stream_key in _streams_cache:
                entry = _streams_cache[stream_key]
                if entry.get("streams"):
                    entry["state"] = "READY"
                else:
                    entry["state"] = "FAILED"
        _update_bg_stats(generation, current="", status_msg="")

    with _bg_lock:
        _bg_thread = threading.Thread(target=worker, daemon=True)
        _bg_thread.start()


def fetch_episode_stream(show_id, ep_number, ttype="sub", quality="best", provider_id=None, exclude_sources=None, ep_data=None):
    if ep_data is None and _episode_data_fn:
        ep_data = _episode_data_fn(show_id, ep_number, ttype, provider_id=provider_id)
    if not ep_data:
        reporting.warn("No episode metadata returned by provider.")
        return None
    sources = ep_data.get("episode", {}).get("sourceUrls", [])
    sources = expand_direct_sources(sources)
    if not sources:
        reporting.warn("0 streaming mirrors found for this episode.")
        return None

    pref = get_preferred_mirror(show_id)
    pref_name = pref.get("source_name", "")
    pref_res = pref.get("resolution", "")

    def dynamic_prio(src):
        api_name = src.get("sourceName", "")
        if pref_name.startswith(api_name) and api_name:
            return 0
        return source_priority(src)

    from ..media.resolver import generate_source_passes
    exclude_sources = exclude_sources or set()
    valid_sources = [s for s in sources if s.get("sourceName", "") not in exclude_sources]
    if not valid_sources:
        reporting.warn("All available mirrors are excluded.")
        return None

    sorted_sources = sorted(valid_sources, key=dynamic_prio)
    total_mirrors = len(sorted_sources)
    mirror_names = [s.get("sourceName", "?") for s in sorted_sources]
    reporting.info(f"Found {total_mirrors} mirror(s): {', '.join(mirror_names[:4])}{'...' if total_mirrors > 4 else ''}")

    retry_announced = False
    for attempt_idx, (src, failed, is_retry, is_final_pass) in enumerate(generate_source_passes(sorted_sources, max_passes=2), 1):
        if is_retry and not retry_announced:
            reporting.warn("Initial pass failed. Retrying failed mirrors (Pass 2/2)...")
            retry_announced = True
        src_name = src.get("sourceName", "?")
        prefix = "Retry " if is_retry else ""
        mirror_num = min(attempt_idx if not is_retry else len(failed) + 1, total_mirrors)
        reporting.info(f"[{prefix}{mirror_num}/{total_mirrors}] Testing mirror: {src_name} ...")
        streams = resolve_source(src)
        if streams:
            selected_stream = streams[0]
            found_pref = False
            if pref_name:
                for s in streams:
                    if s.get("source_name") == pref_name and s.get("resolution", "?") == pref_res:
                        selected_stream = s
                        found_pref = True
                        break
            if not found_pref:
                for s in streams:
                    if quality in s.get("resolution", "") or quality == "best":
                        selected_stream = s
                        break
            reporting.ok(f"Connected: {selected_stream.get('source_name', src_name)} ({selected_stream.get('resolution', '?')})")
            return selected_stream, src.get("sourceName", ""), ep_data, streams
        elif streams is not None:
            failed.append(src)
            reporting.warn(f"[{prefix}{mirror_num}/{total_mirrors}] {src_name} unavailable. Trying next...")

    reporting.warn("All mirrors were tested and failed.")
    return None
