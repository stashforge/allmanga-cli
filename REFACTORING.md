# app_core.py Refactoring Progress

**Goal:** Split `app_core.py` (3512 lines, 191 functions) into cohesive domain modules.

**Strategy:** Each extracted module is a *domain leader* that owns all related logic. `app_core.py` becomes the orchestrator that wires leaders together — it does not do domain work itself.

---

## Design Philosophy (must hold after every phase)

- **Single responsibility.** Every module owns one domain and does only that. It never
  reaches into another module's internals or globals.
- **No responsibility-passing / no hidden chaining.** A module fulfills what it can with
  what it owns, asks a dependency directly for what it needs, and returns the result. It
  does not hand its job off to some third module behind the caller's back.
- **Dependencies point one direction (down the layers).** Higher layers depend on lower
  layers, never the reverse. When a lower layer needs to reach up (e.g. reporting needs to
  draw on the player screen), that is done via an injected hook the top layer wires in — not
  a back-import.
- **Adding a provider / new logic stays independent.** No edit to an unrelated file should
  be required to add a feature. This is the property we must not destroy.

---

## Layered Architecture (extraction goes bottom-up)

```
Layer 0  core/textutils.py   pure helpers: sanitize_terminal_text, _atomic_write_json
              │               (no deps on anything in app_core)
              ▼
Layer 1  core/reporting.py   info/ok/warn/err/debug_warn, spinner + loading helpers
              │               status-sink is INJECTED by app_core (set_status_sink), so
              │               reporting never imports the player screen.
              ▼
Layer 2  core/storage.py     prefs, history, checkpoints, resume/completion, all file I/O
              │               (uses textutils + reporting)
              ▼
Layer 3  core/anilist.py     token/auth, API calls, sync, progress tracking, match/reconcile
         core/streams.py     fetch_episode_stream, source selection, mirror preference
              │               (use storage + reporting)
              ▼
Layer 4  ui/display.py       posters/covers, banners/headers, alt-screen, terminal images
              │
              ▼
         app_core.py         orchestrator: command routing, main(), wiring/DI setup
```

**Why the injection hook:** `info/ok/warn/err` currently write into `_player_ui_state` and
call `render_player_screen()`. That is reporting reaching *up* into the player UI. Instead,
`core/reporting.py` exposes `set_status_sink(fn)`; when no sink is set it just prints. At
startup app_core (or the player screen) registers a sink that appends to the status buffer
and triggers a redraw. Reporting stays a clean bottom layer with zero UI imports.

---

## Progress Tracker

### Pre-Phase: Runtime flags → context.FLAGS ✅ DONE (2026-07-18)
**Decision:** instead of a new `core/runtime.py`, finished the migration the codebase had
already started — `context.CliFlags` (docstring: "all downstream code should read these
instead of `globals().get(...)`").

**What changed:**
- [x] `context.py`: added module-level singleton `FLAGS = CliFlags(...)`, seeded from
      `sys.argv` so pre-argparse calls see correct values
- [x] `app_core.main()`: writes argparse results into `FLAGS`; `flags = runtime_flags`
      (same shared object passed to handlers — mid-run mutations stay visible everywhere)
- [x] `is_incognito()`, `debug_warn()`, `write_private_log()` read `runtime_flags`
- [x] `SYNC_FORCE_ON/OFF`, `SHOW_IMAGE` reads/writes migrated; `_poster_manager` enabled-fn
      reads `runtime_flags.show_image`
- [x] deleted globals: `INCOGNITO_MODE`, `DEBUG_MODE`, `SYNC_FORCE_*`, `SHOW_IMAGE`
- [x] `cli/main.py` crash handler reads `FLAGS.debug_mode`
- [x] tests updated: `test_allmanga_cli_incognito.py`, `test_allmanga_cli_logs.py`,
      `test_allmanga_cli_tui_layout.py` now set `FLAGS.*` (with restore via addCleanup)

**Verified:** full suite 296 passed; only the 3 pre-existing unrelated failures
(stale completion test, token-storage isolation, animexin live-network) remain.

**Why this matters:** bottom-layer functions no longer read `app_core` globals, so they can
now be extracted to `core/` modules without silently losing flag state.

---

### Phase 0: Pure helpers ✅ ALREADY SATISFIED (verified 2026-07-18)
No work needed — the pure bottom layer already exists from earlier refactors:
- `sanitize_terminal_text` → `core/terminal.py`
- `atomic_write_json` / `write_private_text` → `state/io.py`
- `spinner_from_config` / `loading_line` → `ui/spinner.py`, `ui/picker_render.py`
`core/textutils.py` is NOT being created; the plan's Layer 0 maps onto these
existing modules instead.

---

### Phase 1: Reporting ✅ DONE (2026-07-18)
**Created:** `allmanga_cli/core/reporting.py`

**What moved:** `info` / `ok` / `warn` / `err` / `debug_warn`, plus the new
`set_status_sink(fn)` DI hook (sink contract: `sink(message, color) -> bool`,
True = consumed by UI, False = fall back to print).

**What stayed in app_core (deliberately):**
- `_add_status` + `_player_ui_state` — that's player-screen state, not reporting.
  app_core registers `_add_status` as the sink at import time, so behavior is
  byte-for-byte identical.
- `app_core.info/ok/warn/err/debug_warn` remain as aliases (back-compat for
  `configure_reporters(...)` wiring in resolver/android/local_proxy and any
  `app_core.info` callers).
- Spinner/loading helpers (`with_loading`, `_configured_loading_frame`,
  `_spinner_style`) — deferred: they are terminal-render logic entangled with
  alt-screen + PosterManager; they belong with the Phase 4 display work, not
  with reporting. Roadmap updated accordingly.

**Verified:** full suite 296 passed (same 3 pre-existing failures); sink routing
smoke-tested both paths (player inactive → print, active → status buffer +
render trigger).

---

### Phase 2: Storage ✅ DONE (2026-07-19)
**Created:** `allmanga_cli/core/storage.py` (~710 lines)

**What moved (~45 functions):** incognito policy (`is_incognito`, cover cache dir,
cleanup), `_atomic_write_json`, private/exception logs, playback prefs
(load/save + mirror/order/title-sync getters+togglers), resume time, pending
completion, AniList match prefs, watch history (load/save/delete/sanitize/
write-progress/patch/refresh-save), search history, history formatting
delegates, config (load/save/sanitize_token/secure-permissions).

**Design decisions:**
- Paths read via `state.paths` at CALL TIME (`paths.HISTORY_PATH`), never
  imported as constants → tests patch `allmanga_cli.state.paths` in one place.
- `storage.reset_caches()` — official cache-reset API for tests.
- Two upper-layer facts injected via `storage.configure(...)`:
  `episode_ids_fn` (provider catalogs) and `prepare_display_state_fn`
  (display priming). `configure_redactor(...)` injects log redaction.
  app_core wires all three after its defs. No upward imports.
- app_core keeps `name = storage.name` aliases for every moved function —
  all existing callers (app/, ui/, cli/, tests) work unchanged.
- `prepare_show_display_state`, `playback_ep_from_history_entry`,
  `episode_id_for_progress` callers of ensure_episode_ids stay in app_core
  (provider-layer coupling); AniList queue + history-refresh-from-AniList
  deliberately deferred to Phase 3a (they are AniList domain, not storage).

**Test updates (4 files, old `__globals__` patching → paths patching):**
- `test_allmanga_cli_logs.py` → `patch.object(paths, "LOG_DIR", ...)`
- `test_allmanga_cli_history_refresh.py` → paths + `storage.reset_caches()`
- `test_allmanga_cli_incognito.py` → paths + reset; queue path still set via
  app_core ns (queue moves in Phase 3a)
- `test_allmanga_cli_token_storage.py` → `paths.CONFIG_PATH`; also fixed the
  pre-existing isolation bug (test read the real secret-backend token)

**Verified:** suite 297 passed / 2 pre-existing failures (was 296/3 — the
token-storage isolation failure is now FIXED). End-to-end smoke test: prefs,
resume, history, mirror-pref roundtrips through app_core aliases against a
temp dir. app_core: 3512 → 3023 lines.

---

### Phase 3a: AniList 🔶 IN PROGRESS (2026-07-19)
**Created:** `allmanga_cli/core/anilist.py`

**Sub-commit 1 DONE — auth + API + read-cache cluster (21 funcs):**
token/auth (save/clear/status/mask/stored/auth-lines/prompt), media+id
helpers (fetch_media, get_show_anilist_id/mal_id/media_id,
update_anime_from_anilist_media), list/search (fetch_anilist_list,
search_anilist) + shared `_anilist_list_cache`/`_anilist_search_cache`,
entry writes (scrobble, date-updates, update_anilist_entry).
- ANSI colours declared locally (matches per-module convention).
- Read caches live in core.anilist; app_core keeps SAME-OBJECT aliases so
  invalidation on write still crosses (verified via identity smoke test).
- app_core aliases every moved name; callers/tests unchanged.
- Verified: 297 passed / 2 pre-existing failures.

**Sub-commit 2 TODO — sync + queue + reconcile (the hard half):**
sync_progress_and_checkpoint, sync_watched_to_anilist, save_and_sync_watched,
should_update_anilist_progress; the threaded write-queue (_load/_save_queue,
_enqueue, _run_queued, _anilist_write_worker, _start_queued,
queue_anilist_progress, retry/flush); reconcile_progress, _push_local_progress,
_import_anilist_progress; refresh_history_entry_from_anilist +
refresh_history_anilist_airing_batch.
Cross-domain couplings needing injected hooks: set_action_feedback (UI toast),
refresh_history_entry_allanime_catalog (provider catalog), ensure_episode_ids.
**Target:** `allmanga_cli/core/anilist.py`

- [ ] token/auth: `stored_anilist_token`, `save_anilist_token`, `clear_anilist_token`, `anilist_token_storage_status`, `anilist_auth_*`, `prompt_anilist_token`
- [ ] API: `fetch_anilist_media`, `fetch_anilist_list`, `load_anilist_browse`
- [ ] sync: `sync_watched_to_anilist`, `sync_progress_and_checkpoint`, `save_and_sync_watched`, `should_update_anilist_progress`
- [ ] progress/match: `get_show_anilist_id`, `get_anilist_media_id`, match/reconcile helpers

**Steps:** create → move → re-export → verify → commit
Commit: "refactor: extract AniList operations to core/anilist.py"

### Phase 3b: Streams ⬜ NOT STARTED
**Target:** `allmanga_cli/core/streams.py`

- [ ] `fetch_episode_stream()`
- [ ] source selection / quality filtering
- [ ] mirror-preference glue (reads storage)

**Steps:** create → move → re-export → verify → commit
Commit: "refactor: extract stream resolution to core/streams.py"

---

### Phase 4: UI Display ⬜ NOT STARTED
**Target:** `allmanga_cli/ui/display.py`

- [ ] poster: `_get_poster`, `_request_poster_redraw`, `_clear_poster_downloads`, `_poster_footer_line`, `_poster_needs_tick`, `_poster_manager`
- [ ] terminal images: `clear_terminal_images`
- [ ] alt screen: `enter_alt_screen`, `exit_alt_screen`
- [ ] banners/headers: `print_app_banner`, `print_episode_header`

**Steps:** create → move → re-export → verify → commit
Commit: "refactor: extract UI display helpers to ui/display.py"

---

### Phase 5: Final Cleanup ⬜ NOT STARTED
- [ ] Replace back-compat shims with direct imports in callers (only where safe)
- [ ] Confirm no circular imports (`python3 -c "from allmanga_cli.cli.main import run"`)
- [ ] Run full test suite
- [ ] Update this doc's final status
- [ ] Commit: "refactor: finalize app_core.py split"

---

## Verification Checklist (run after EACH phase)

```bash
# imports
python3 -c "from allmanga_cli import app_core; print('OK app_core')"
python3 -c "from allmanga_cli.cli.main import run; print('OK CLI loads')"
# per-phase module (add as they exist)
python3 -c "from allmanga_cli.core import textutils; print('OK textutils')"   # P0+
python3 -c "from allmanga_cli.core import reporting; print('OK reporting')"   # P1+
python3 -c "from allmanga_cli.core import storage;   print('OK storage')"     # P2+
python3 -c "from allmanga_cli.core import anilist;   print('OK anilist')"     # P3a+
python3 -c "from allmanga_cli.core import streams;   print('OK streams')"     # P3b+
python3 -c "from allmanga_cli.ui   import display;   print('OK display')"     # P4+
# tests + size
python3 -m pytest -q
wc -l allmanga_cli/app_core.py
```

**Rule:** never end a phase with app_core in a non-importable state. If a phase can't
finish cleanly, revert the partial move rather than leaving broken files.

---

## Ground rules
- Bottom-up only. Never extract a layer before the layer it depends on.
- One phase = one working, committed state.
- Back-compat shim (`from .core.x import ...` in app_core) keeps every existing caller working
  until Phase 5 tidies imports.
- Dependencies point down; lower layers reach up only through injected hooks.

---

## Current Status
- **Started:** 2026-07-18
- **Last updated:** 2026-07-18
- **Lines remaining in app_core.py:** 3512
- **Decision log:**
  - `core/logging.py` → **`core/reporting.py`** (avoid shadowing stdlib `logging`)
  - reporting↔player-screen coupling → **dependency injection** via `set_status_sink()`
  - Added **Layer 0** (`core/textutils.py`) for pure helpers everything depends on
