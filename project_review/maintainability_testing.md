# Maintainability And Testing Findings

## Project Risks

### MAINT-01: The active script has no real version-control repository

`.git` is an empty directory, so there is no usable commit history, diff,
branching, or recovery workflow. The backup folders are valuable snapshots but
are not a replacement for version control.

Priority: critical project hygiene.

### MAINT-02: Existing tests do not cover allmanga-cli

`tests/test_scraper.py` tests the separate `axcli` package. Test discovery ran
zero tests in the current layout, and running the test file directly failed to
import `axcli`. No test imports or exercises `allmanga-cli`.

Priority: critical before broad refactoring.

### MAINT-03: Single-file architecture is beyond a safe maintenance size

The script is 5,669 lines with about 248 function definitions and 246 top-level
statements. TUI, storage, HTTP, AniList, matching, stream resolution, downloads,
platform integration, and the state machine share one namespace.

Priority: high, but split only after characterization tests exist.

### MAINT-04: Runtime behavior depends on many implicit globals

Navigation, selected title, caches, poster state, sync flags, streams, player
state, and callbacks are stored through module globals and `globals()`.

Impact: hidden coupling, stale state between screens, and difficult tests.

Fix direction: introduce `AppState`, `NavigationState`, `PlaybackState`, and
service objects incrementally.

### MAINT-05: Broad exception handling hides defects

There are many `except Exception` and silent `pass` blocks across networking,
threads, poster rendering, IPC, storage, and parsing.

Fix direction: catch expected exception classes, return typed failures, and send
unexpected exceptions to structured debug logging.

### MAINT-06: Data models are untyped mutable dictionaries

AllAnime objects, AniList objects, history objects, streams, and UI-only fields
are merged into the same dictionaries.

Impact: provider IDs can be confused, display mutations are persisted, and field
requirements are undocumented.

Fix direction: use dataclasses/TypedDict models for `Anime`, `Episode`,
`HistoryEntry`, `Stream`, and `AniListState`; keep provider and UI fields
separate.

### MAINT-07: Persistent JSON has no schema version or migration layer

Config, history, and playback files evolve through ad hoc field checks.

Fix direction: add `schema_version`, validators, migrations, and fixtures for
old versions.

### MAINT-08: HTTP behavior is duplicated

Timeouts, headers, JSON parsing, GraphQL errors, TLS contexts, and error handling
vary across direct urllib calls.

Fix direction: one HTTP client wrapper with policies for AniList, provider API,
media probes, and covers.

### MAINT-09: Similar screen flows remain duplicated

AllAnime search, AniList search, list browsing, manual match, Details actions,
and progress/status pickers repeat state transitions and object setup.

Fix direction: extract screen controllers after navigation tests are in place.

### MAINT-10: Dependency and packaging metadata describe another application

`pyproject.toml` packages `axcli`, not `allmanga-cli`. The active script has no
declared package, version, install entry point, or tested dependency matrix.

Fix direction: decide whether these are one project or two; give allmanga-cli
its own package metadata and release process.

## Required Test Layers

1. Pure unit tests:
   - episode catalogs, gaps, decimals, ordering, and progress mapping
   - matching score and reject rules
   - completion thresholds and played-time accounting
   - history reconciliation and status transitions
   - metadata formatting and navigation decisions
2. Storage tests:
   - atomic writes, permissions, corruption recovery, migrations
3. HTTP contract tests with recorded/mock responses:
   - AniList success/errors/rate limits
   - provider result and episode-detail variants
4. Concurrency tests:
   - stale mirror workers
   - poster worker cancellation
   - durable sync queue and shutdown
5. TUI state-machine tests:
   - Esc/Left parent behavior
   - single-result and no-result flows
6. Player integration tests using a fake mpv IPC server.
7. Termux command-generation tests without launching Android activities.

## Tooling Baseline

- `ruff` for lint/format
- `mypy` or pyright after models are introduced
- `pytest` with coverage
- `bandit` as a secondary security signal
- CI on supported Python versions
- pre-commit checks for compile, tests, and accidental secrets
