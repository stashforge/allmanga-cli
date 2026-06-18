# Modularization Plan

The `allmanga_cli` package is the runtime source of truth. Installed users get
the `allmanga-cli` console script from `pyproject.toml`; source-tree users run
`python -m allmanga_cli`.

## Extraction Order

1. `cli/` - command routing, argument parsing, help, and installed entry point.
2. `core/` - terminal primitives, bounded API reads, and process handling.
3. `state/` - paths, config IO, atomic writes, and preference mutations.
4. `services/` - AllAnime and AniList HTTP requests and normalization.
5. `domain/` - episodes, matching, titles, metadata, tracking, and history rules.
6. `media/` - source resolution, DASH, downloads, URLs, and local proxying.
7. `playback/` - mpv IPC, Android launching, runtime files, and completion rules.
8. `ui/` - cover helpers, fallback input, and reusable help content.
9. `app_core.py` - remaining stateful TUI orchestration.
10. `app.py` - compatibility exports.

## Current Status

Completed boundaries:

- CLI parsing and package entry points
- terminal, process, API, config, state IO, and cached-list persistence helpers
- AniList and AllAnime request services
- episode, matching, metadata, title, tracking, sorting, history, and progress
  reconciliation rules
- source resolution, DASH, downloads, download-library scanning, and proxying
- mpv IPC/runtime handling and Android player launching
- cover validation/rendering helpers and non-TTY fallback input

Still intentionally in `app.py`:

- alternate-screen picker state and screen composition
- cover download coordination and redraw state
- local history cache write orchestration
- AniList write worker and reconciliation side effects
- the interactive application state machine

These areas share mutable session state. They should move behind explicit runtime
objects rather than importing or duplicating `app.py` globals.

## Rules

- Keep `python -m allmanga_cli` and the installed console script working.
- Preserve public function names used by tests until their callers are migrated.
- Do not combine feature changes with extraction commits.
- Run focused tests and the full AllManga suite after every extraction.
- Use Git commits instead of creating whole-script backup folders.
