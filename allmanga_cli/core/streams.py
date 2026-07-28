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

import threading
from typing import Optional

from ..media.resolver import resolve_source
from ..media.sources import source_priority
from .storage import get_preferred_mirror

YELLOW = "\033[1;33m"
RESET = "\033[0m"

_episode_data_fn = None


def expand_direct_sources(sources: list) -> list:
    """
    If a source provides a direct `link` to a media file (.m3u8, .mp4),
    automatically duplicate it as a `sourceUrl` entry. This allows the 
    resolver to spawn a background yt-dlp worker to extract adaptive 
    qualities (e.g. 720p, 1080p), while still preserving the instant 
    playback of the direct `link` entry.
    """
    expanded = []
    for src in sources:
        expanded.append(src)
        url = src.get("link") or src.get("streamUrl")
        
        if url and (".m3u8" in url or ".mp4" in url):
            if "Yt-Dlp" not in src.get("sourceName", ""):
                ytdl_src = src.copy()
                ytdl_src.pop("link", None)
                ytdl_src.pop("streamUrl", None)
                
                ytdl_src["sourceUrl"] = url
                base_name = src.get("sourceName", "Direct").replace(" Direct", "")
                ytdl_src["sourceName"] = f"{base_name} Yt-Dlp"
                expanded.append(ytdl_src)
    return expanded


def configure(*, episode_data_fn=None):
    """Inject the provider episode-catalog lookup (see module docstring)."""
    global _episode_data_fn
    if episode_data_fn is not None:
        _episode_data_fn = episode_data_fn


# all_streams is the shared list for the current episode.
# Both _streams_lock and _bg_lock are used to synchronize access.
all_streams: list = []
_streams_lock = threading.Lock()  # guards all_streams reads/writes
_streams_generation = 0  # invalidates workers started for an older episode
_bg_thread = None  # type: Optional[threading.Thread]
_bg_lock = threading.Lock()  # guards _bg_thread and _bg_stats
_bg_generation = 0
_bg_stats = {"resolved": 0, "failed": 0, "total": 0, "current": ""}


def _clear_streams():
    global _streams_generation
    with _streams_lock:
        _streams_generation += 1
        all_streams.clear()
        return _streams_generation


def _extend_streams(streams):
    with _streams_lock:
        all_streams.extend(streams)


def _stream_snapshot():
    with _streams_lock:
        return list(all_streams)


def _stream_count():
    with _streams_lock:
        return len(all_streams)


def _publish_stream(stream, generation):
    """Publish a resolved stream only while its episode generation is current."""
    link = stream.get("link")
    with _streams_lock:
        if generation != _streams_generation:
            return False
        if link and any(existing.get("link") == link for existing in all_streams):
            return False
        all_streams.append(stream)
        return True


def _generation_is_current(generation):
    with _streams_lock:
        return generation == _streams_generation


def _update_bg_stats(generation, *, current=None, resolved=0, failed=0):
    with _bg_lock:
        if generation != _bg_generation:
            return False
        if current is not None:
            _bg_stats["current"] = current
        _bg_stats["resolved"] += resolved
        _bg_stats["failed"] += failed
        return True


def start_bg_resolve(ep_data, exclude_names: set):
    """
    Start resolving all remaining sources in background.
    Call after the first stream is already playing.
    exclude_names: source names already resolved (skip them to avoid duplicates).
    """
    global _streams_generation, _bg_thread, _bg_generation, _bg_stats
    sources = ep_data.get("episode", {}).get("sourceUrls", [])
    sources = expand_direct_sources(sources)
    sources = sorted(sources, key=source_priority)
    with _streams_lock:
        _streams_generation += 1
        generation = _streams_generation
        seen_links = {s.get("link") for s in all_streams}
    with _bg_lock:
        _bg_generation = generation
        _bg_stats = {"resolved": len(exclude_names), "failed": 0, "total": len(sources), "current": ""}

    def worker():
        from ..media.resolver import generate_source_passes
        for src, failed_queue, is_retry, is_final_pass in generate_source_passes(sources, max_passes=3):
            if not _generation_is_current(generation):
                return
            sname = src.get("sourceName", "")
            if sname in exclude_names:
                continue
            if not _update_bg_stats(generation, current=sname):
                return
            try:
                found = False
                for stream in resolve_source(src, silent=True):
                    if not _generation_is_current(generation):
                        return
                    link = stream.get("link")
                    if link not in seen_links and _publish_stream(stream, generation):
                        seen_links.add(link)
                        found = True
                        
                if not found:
                    if not is_final_pass:
                        failed_queue.append(src)
                
                # We only increment resolved on success. We only increment failed if it permanently failed the final pass.
                inc_failed = 1 if not found and is_final_pass else 0
                inc_resolved = 1 if found else 0
                
                # Only update stats if we actually hit a permanent conclusion (found, or final pass failed)
                if inc_resolved or inc_failed:
                    if not _update_bg_stats(
                        generation,
                        resolved=inc_resolved,
                        failed=inc_failed
                    ):
                        return
            except Exception:
                if not is_final_pass:
                    failed_queue.append(src)
                else:
                    if not _update_bg_stats(generation, failed=1):
                        return
        _update_bg_stats(generation, current="")

    with _bg_lock:
        _bg_thread = threading.Thread(target=worker, daemon=True)
        _bg_thread.start()


def fetch_episode_stream(show_id, ep_number, ttype="sub", quality="best", provider_id=None, exclude_sources=None):
    ep_data = _episode_data_fn(show_id, ep_number, ttype, provider_id=provider_id)
    if not ep_data:
        return None
    sources = ep_data.get("episode", {}).get("sourceUrls", [])
    sources = expand_direct_sources(sources)
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
    for src, failed, _, _ in generate_source_passes(sorted(valid_sources, key=dynamic_prio), max_passes=3):
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
            return selected_stream, src.get("sourceName", ""), ep_data, streams
        elif streams is not None:
            failed.append(src)
    return None
