"""Asynchronous live search workers and query coordination."""

from __future__ import annotations

import os
import threading
from typing import Any, Callable

from ..core.api import SearchFailure, search_failure_message
from ..core.reporting import debug_warn
from ..core.storage import load_config, write_exception_log

from ..core.enrichment import enrich_provider_results
from ..providers import provider_key, provider_display_name
from ..services.catalog import search_anime
from ..core.anilist import search_anilist
from ..ui.spinner import spinner_from_config
from ..ui.picker_render import loading_line as _loading_line
from ..ui import display

_provider_search_cache = {}


def make_provider_oneshot_search(query: str, ttype: str, provider_id: str | None = None):
    loading = True
    results = []
    error = ""
    cfg = load_config()
    spinner_style = spinner_from_config(cfg)
    token = cfg.get("anilist_token")
    
    from ..context import FLAGS as runtime_flags
    use_sync = runtime_flags.sync_force_on or (cfg.get("sync") and not runtime_flags.sync_force_off)
    if not use_sync:
        token = ""

    provider_id = provider_key(provider_id)
    provider_name = provider_display_name(provider_id)
    cache_key = (query, ttype, provider_id)

    if cache_key in _provider_search_cache:
        loading = False
        results = _provider_search_cache[cache_key]
        
        def get_results(): return results
        def get_loading(): return ""
        def get_error(): return ""
        def live_fn(q=""):
            opts = [f"{s.get('name')}" for s in results]
            return opts, "", True
            
        return live_fn, get_results, get_loading, get_error

    def _fetch():
        nonlocal loading, results, error
        try:
            shows = None
            al_shows = None

            def _fetch_aa():
                nonlocal shows, error
                try:
                    shows = search_anime(
                        query,
                        ttype,
                        raise_errors=True,
                        provider_id=provider_id,
                    )
                except SearchFailure as exc:
                    error = str(exc)
                    shows = []
            def _fetch_al():
                nonlocal al_shows
                al_shows = search_anilist(token, query)

            threads = [threading.Thread(target=_fetch_aa)]
            if token:
                threads.append(threading.Thread(target=_fetch_al))

            for t in threads: t.start()
            for t in threads: t.join()

            if shows:
                shows = enrich_provider_results(shows, token, al_shows)

            if shows:
                for s in shows:
                    if s.get("status") == "NOT_YET_RELEASED":
                        continue
                    results.append(s)
                _provider_search_cache[cache_key] = list(results)

        except Exception as e:
            if not error:
                error = search_failure_message(provider_name, e)
            try:
                write_exception_log("bg_crash.log")
            except Exception as log_error:
                debug_warn("Failed to write background crash log", log_error)
        finally:
            loading = False

    threading.Thread(target=_fetch, daemon=True).start()

    def get_results():
        return results

    def get_loading():
        if loading:
            try: w = os.get_terminal_size().columns
            except OSError: w = 80

            msg = "Searching…"
            return _loading_line(msg, w, spinner_style)
        return ""

    def get_error():
        return error

    def live_fn(q=""):
        opts = [f"{s.get('name')}" for s in results]
        return opts, get_loading(), not loading

    return live_fn, get_results, get_loading, get_error


def make_allanime_oneshot_search(query: str, ttype: str, provider_id: str | None = None):
    return make_provider_oneshot_search(query, ttype, provider_id)


def make_anilist_oneshot_search(token: str, initial_query: str):
    results = []
    loading = True
    error = ""
    spinner_style = display._spinner_style

    def worker():
        nonlocal results, loading, error
        try:
            res = search_anilist(token, initial_query, raise_errors=True)
            if res:
                results = res
        except SearchFailure as exc:
            error = str(exc)
        finally:
            loading = False

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def get_loading():
        if loading:
            try: w = os.get_terminal_size().columns
            except OSError: w = 80

            return _loading_line("Searching…", w, spinner_style)
        return ""

    def live_fn(q=""):
        opts = [f"{s['name']}" for s in results]
        return opts, get_loading(), not loading

    return live_fn, lambda: list(results), get_loading, lambda: error


def _cached_search_results(query_str, query_key, shows_key, make_search):
    import allmanga_cli.app_core as app_core
    if query_str == getattr(app_core, query_key, None) and getattr(app_core, shows_key, None):
        shows = getattr(app_core, shows_key)
        return None, lambda: shows, lambda: "", lambda: ""
    return make_search()


def _remember_search_results(query_str, shows, query_key, shows_key):
    if shows:
        import allmanga_cli.app_core as app_core
        setattr(app_core, query_key, query_str)
        setattr(app_core, shows_key, shows)
