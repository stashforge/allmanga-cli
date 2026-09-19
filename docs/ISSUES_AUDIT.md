# AllManga-CLI Code Audit - Issues List

**Generated**: 2026-09-18  
**Scope**: Core CLI only (excluding `web/` directory)  
**Files Analyzed**: ~50 Python modules across `allmanga_cli/`, `tests/`

---

## 🔴 Critical / Logic Bugs

### 1. Race Condition in Stream Generation Counter
**File**: `allmanga_cli/core/streams.py:331-333`  
**Function**: `start_bg_resolve()`  
**Issue**: `_streams_generation` incremented inside lock, but `_bg_generation` assigned outside lock. Another `_clear_streams()` call between increment and assignment causes background worker to use stale generation.  
**Impact**: Background resolution may validate/publish streams for previous episode.  
**Fix**: Move `_bg_generation = generation` inside `_streams_lock` block.

---

### 2. Mutable Shared State in FSM Handlers
**File**: `allmanga_cli/app/orchestrator.py:508-535`  
**Issue**: `flags`, `ui`, `ms`, `cfg`, `args` passed to every state handler. All mutable, shared across entire FSM loop. Handlers mutate `ui.ui_show_ctx`, `ui.ui_ttype_ctx`, `ms` fields without clear ownership.  
**Impact**: Hard to track mutations; subtle bugs on state transitions; testing difficult.  
**Fix**: Consider immutable state snapshots or explicit state transition returns.

---

### 3. `resolveTracking` Closure Captures Stale `ui` Reference
**File**: `allmanga_cli/app/orchestrator.py:390-407`  
**Issue**: `resolveTracking` defined inside `main()` captures `ui` from outer scope. If `ui` ever replaced (architecture allows), closure holds stale reference.  
**Impact**: Sync logic may use wrong show context.  
**Fix**: Pass `ui` as parameter or use `get_ui_show(ui)` helper consistently.

---

### 4. Thread Safety: `_in_flight_catalog_tasks` Cleanup on Exception
**File**: `allmanga_cli/services/catalog.py:172-174`  
**Function**: `_perform_catalog_fetch()`  
**Issue**: `finally` block calls `_in_flight_catalog_tasks.pop()` but `fatal_terminal_exit()` calls `os._exit()` before cleanup runs.  
**Impact**: Stale futures remain; subsequent calls for same show/ttype may reuse "completed" future incorrectly.  
**Fix**: Register cleanup via `atexit` or handle `ProviderDependencyError` without `os._exit()`.

---

### 5. Double-Check Locking Pattern Broken in `ensure_episode_ids`
**File**: `allmanga_cli/services/catalog.py:198-202`  
**Issue**: Task submission inside lock, but `fut.result()` called outside. Another thread can submit duplicate task for same key between lock release and `.result()`.  
**Impact**: Duplicate catalog fetches; wasted API calls.  
**Fix**: Use `fut = _in_flight_catalog_tasks.setdefault(task_key, _catalog_executor.submit(...))` pattern.

---

## 🟠 Performance / Optimization Issues

### 6. Inefficient Cache Invalidation in `_stream_snapshot`
**File**: `allmanga_cli/core/streams.py:158-177`  
**Issue**: Every call iterates all cached streams and calls `is_stream_valid_fast()` (full validation). Called frequently during UI rendering.  
**Impact**: UI lag with many cached streams; redundant validation.  
**Fix**: Track validity per-stream with timestamps; only re-validate expired entries.

---

### 7. Repeated `load_config()` Calls in Hot Paths
**Files**: Multiple  
- `orchestrator.py:146, 286, 422`
- `search_coordinator.py:30`
- `storage.py` (multiple functions)  
**Issue**: `load_config()` reads/parses JSON from disk on every call.  
**Impact**: Unnecessary disk I/O on every search, config command, state transition.  
**Fix**: Cache config in memory; invalidate on explicit `save_config()`.

---

### 8. `_provider_search_cache` Unbounded Growth
**File**: `allmanga_cli/app/search_coordinator.py:23`  
**Issue**: Module-level dict caches search results indefinitely with no TTL or size limit.  
**Impact**: Memory leak over long sessions with many searches.  
**Fix**: Add LRU eviction (e.g., `functools.lru_cache` or custom bounded dict).

---

### 9. Redundant Sorting in `fetch_episode_stream`
**File**: `allmanga_cli/core/streams.py:502`  
**Issue**: `sorted(valid_sources, key=dynamic_prio)` sorts ALL sources O(n log n), but `generate_source_passes()` iterates sequentially anyway.  
**Impact**: Unnecessary CPU on episode start (especially many mirrors).  
**Fix**: Remove sort; let `generate_source_passes` handle priority via its internal logic.

---

### 10. ThreadPoolExecutor Never Shutdown
**File**: `allmanga_cli/services/catalog.py:130`  
**Issue**: `_catalog_executor = ThreadPoolExecutor(max_workers=4)` created at module load, never shut down.  
**Impact**: Threads persist after CLI exit; interferes with test runners/repeated imports.  
**Fix**: Add `atexit.register(_catalog_executor.shutdown)` or context manager.

---

## 🟡 Clean Code / Architecture Issues

### 11. `app_core.py` is a 621-line "God Module" Facade
**File**: `allmanga_cli/app_core.py`  
**Issue**: Re-exports 241+ symbols from 30+ modules via import aliases. Creates tight coupling - everything imports from `app_core` instead of proper modules. Violates dependency inversion.  
**Impact**: Circular import risk; hard to refactor; tests mock `app_core` instead of real modules; IDE navigation broken.  
**Fix**: Remove facade; update imports to point to actual modules. Use `app_core.py` only for true cross-cutting concerns.

---

### 12. Global State via `globals()` Pattern Persists
**Files**: Multiple  
- `orchestrator.py:154, 374, 407` - `globals()["SUPPRESS_FINAL_CURSOR_RESTORE"]`, `globals()["_download_batch_end"]`, `globals()["resolveTracking"]`
- `picker.py:75` - `_needs_redraw` module global
- `streams.py` - multiple module globals (`_streams_generation`, `_bg_thread`, etc.)  
**Issue**: Despite `context.py` introducing `FLAGS`, `UiState`, `MachineState`, several modules still use `globals()`.  
**Impact**: Hidden dependencies; hard to test; state leaks between runs.  
**Fix**: Migrate all `globals()` usage to proper state objects or module-level singletons with clear APIs.

---

### 13. Inconsistent Error Handling Patterns
**Scope**: Throughout codebase  
**Issue**: Mix of:
- Exceptions raised/caught locally
- `debug_warn()` + returning `None`/`[]`/`False`
- `fatal_terminal_exit()` (calls `os._exit()`)
- `err()`/`warn()` logging + return
- `SearchFailure` custom exceptions  
**Impact**: Unpredictable error propagation; callers don't know what to handle.  
**Fix**: Define clear error hierarchy; document which functions raise vs return error sentinels.

---

### 14. Hardcoded ANSI Colors Scattered Everywhere
**Files**: 20+ files including `orchestrator.py`, `picker.py`, `app_core.py`, `anilist.py`, `display.py`, `reporting.py`  
**Issue**: Color constants (`GREEN`, `RED`, `CYAN`, `BOLD`, `RESET`, Catppuccin palette) duplicated.  
**Impact**: Theme changes require editing 20+ files; no centralized theming.  
**Fix**: Create `ui/colors.py` with theme constants; import everywhere.

---

### 15. Massive `tui_pick()` Function (1000+ lines)
**File**: `allmanga_cli/ui/picker.py:106-1031`  
**Issue**: Single function handles rendering, input handling, live updates, poster management, multi-select, help display, search filtering, cursor animation. Violates SRP.  
**Impact**: Extremely hard to maintain; bugs in one feature affect others; testing nearly impossible.  
**Fix**: Split into classes: `PickerRenderer`, `PickerInputHandler`, `PickerLiveUpdater`, `PosterManager` integration.

---

### 16. Circular Import via `app_core` ↔ `context` ↔ `orchestrator`
**Files**: 
- `orchestrator.py` imports `from .. import app_core`
- `app_core.py` imports `from allmanga_cli.app.orchestrator import main`
- `context.py` imports from `sys.argv` at module level  
**Impact**: Module load order fragility; potential initialization bugs.  
**Fix**: Break cycle - move `main` re-export to separate module or use lazy imports.

---

### 17. Injection Pattern Inconsistency
**Files**: Multiple modules  
**Issue**: Some modules use `configure(fn)` pattern (`storage.py`, `streams.py`, `anilist.py`, `display.py`), others use direct imports from `app_core`. No consistent DI framework.  
**Impact**: Confusing architecture; some dependencies explicit, others implicit globals.  
**Fix**: Standardize on `configure()` pattern for all cross-layer dependencies.

---

### 18. Provider Registry Loads JSON at Import Time
**File**: `allmanga_cli/providers/__init__.py:30-35`  
**Issue**: `PROVIDER_REGISTRY` loaded from `registry.json` at module import. Fails silently (empty dict) if file missing.  
**Impact**: Hard to test with custom registries; silent failures; import-time I/O.  
**Fix**: Lazy-load registry on first access; add explicit `load_registry()` function.

---

### 19. `MachineState` Has 20+ Fields with Unclear Ownership
**File**: `allmanga_cli/context.py:143-221`  
**Issue**: Fields like `ep_cache_key`, `ep_cache_data`, `last_aa_query_str`, `last_aa_shows`, `last_al_query_str`, `last_al_shows`, `download_batch_end` mixed with core state. No encapsulation.  
**Impact**: Any handler can mutate any field; no invariants enforced.  
**Fix**: Split into focused dataclasses: `SearchState`, `PlaybackState`, `CacheState`, `NavigationState`.

---

### 20. `CliFlags` Seeded from `sys.argv` at Module Load
**File**: `allmanga_cli/context.py:62-66`  
**Issue**: `FLAGS` singleton initialized with `sys.argv` before `argparse` runs. If imported early (e.g., in tests), sees wrong args.  
**Impact**: Test flakiness; incorrect debug/incognito detection in some contexts.  
**Fix**: Initialize `FLAGS` in `main()` after parsing; provide `FLAGS.update_from_args(args)` method.

---

## 🔵 Maintainability / Technical Debt

### 21. No Type Hints on Public APIs
**Scope**: Most modules  
**Issue**: Many public functions lack return type annotations or have `Any` types. `tui_pick()` has 30+ params with `TYPE_CHECKING` imports only.  
**Impact**: IDE support limited; refactoring risky; no static analysis.  
**Fix**: Add type hints incrementally; enable `mypy` in CI.

---

### 22. Magic Strings for State Names
**File**: `allmanga_cli/app/orchestrator.py:503-536`  
**Issue**: State machine uses string literals: `"SEARCH"`, `"DETAILS"`, `"PLAY"`, etc. No enum or constants.  
**Impact**: Typos cause runtime errors; no IDE autocomplete; hard to visualize all states.  
**Fix**: Create `State` enum; use throughout FSM.

---

### 23. Provider Capability Detection via String Matching
**Files**: `streams.py:317-321`, `catalog.py:220-223`  
**Issue**: `is_donghua = str(provider_id or "").lower() in {"animexin", "lucifer", "animekhor"}` - hardcoded provider IDs in stream sorting logic.  
**Impact**: Adding new providers requires modifying core stream logic; violates OCP.  
**Fix**: Add `Provider.capability` property or metadata in `registry.json`.

---

### 24. `_provider_search_cache` Key Doesn't Account for Config Changes
**File**: `allmanga_cli/app/search_coordinator.py:41`  
**Issue**: `cache_key = (query, ttype, provider_id)` but cache doesn't account for config changes (quality, sync settings) that affect results.  
**Impact**: Stale results when user changes config mid-session.  
**Fix**: Include relevant config hash in cache key; or invalidate cache on config change.

---

### 25. Duplicate Episode ID Normalization Logic
**Files**: `domain/episodes.py`, `storage.py`, `catalog.py`  
**Issue**: `_normalize_episode_ids`, `episode_id_for_progress`, `clean_episode_identifier`, `parse_episode_dual_numbers` scattered.  
**Impact**: Inconsistent behavior; bug fixes need applying in multiple places.  
**Fix**: Consolidate into single `domain/episodes.py` module; export canonical functions.

---

## 🟢 Testing / Quality Gaps

### 26. Tests Only Cover Domain Logic, Not Integration
**Directory**: `tests/`  
**Issue**: Tests exist for `domain/history`, `domain/metadata`, `providers/shared/wordpress`, but no tests for:
- FSM state transitions
- Stream resolution pipeline
- Playback engine
- Provider search/episode fetching
- Config/keyring integration  
**Impact**: Regressions in core flows undetected.  
**Fix**: Add integration tests using `pytest` with mocked providers/network.

---

### 27. No Linting/Typechecking Configuration Found
**Scope**: Repo root  
**Issue**: No `pyproject.toml`, `ruff.toml`, `mypy.ini`, or `pylintrc`.  
**Impact**: No enforced code style; no CI checks for types/lint.  
**Fix**: Add `pyproject.toml` with `ruff`, `mypy`, `pytest` config.

---

### 28. `secret-tool` Dependency Not Abstracted
**Files**: `allmanga_cli/state/secrets.py`, `storage.py:864-875`  
**Issue**: Direct calls to `secret-tool` CLI. No interface for mocking in tests; fails on systems without SecretService.  
**Impact**: Tests can't run in CI without keyring; hard to test token storage logic.  
**Fix**: Create `SecretStore` protocol/interface; implement `KeyringSecretStore` and `FileSecretStore`; inject via DI.

---

## Summary by Category

| Category | Count | Highest Priority |
|----------|-------|------------------|
| Critical Logic Bugs | 5 | Race condition in stream generation |
| Performance | 5 | Unbounded search cache, repeated config loads |
| Clean Code/Architecture | 10 | God module `app_core.py`, global state, massive `tui_pick()` |
| Maintainability | 5 | Magic strings, hardcoded provider IDs, no types |
| Testing/Quality | 3 | No integration tests, no lint config, unmockable secrets |

---

## Suggested Fix Priority Order

1. **Critical**: Stream generation race condition (#1), ThreadPoolExecutor shutdown (#10), `_in_flight_catalog_tasks` cleanup (#4)
2. **Architecture**: Replace `app_core.py` facade (#11), standardize injection pattern (#17), migrate `globals()` (#12)
3. **Performance**: Config caching (#7), bounded search cache (#8), remove redundant sort (#9)
4. **Maintainability**: Type hints (#21), State enum (#22), provider capability metadata (#23)
5. **Testing**: Lint config (#27), secret abstraction (#28), integration tests (#26)

---

## Discussion Notes

- [ ] **Issue #11 (app_core.py)**: Biggest architectural win but highest effort. Phase incrementally?
- [ ] **Issue #15 (tui_pick)**: Could extract `Picker` class first, keep function as thin wrapper.
- [ ] **Issue #19 (MachineState)**: Split dataclasses would clarify FSM handler signatures.
- [ ] **Issue #23 (provider capabilities)**: Requires registry.json schema change + provider updates.
- [ ] **Issue #28 (secrets)**: Need to decide: keep `secret-tool` as primary, file fallback for Termux?

---

*Add discussion notes, decisions, and fix PR references here as work progresses.*