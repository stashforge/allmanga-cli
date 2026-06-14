# Modularization Plan

The `allmanga-cli` executable remains the user-facing entry point. Runtime
behavior is moved incrementally into the `allmanga_cli` package, one tested
boundary per commit.

## Extraction Order

1. `cli/` - command routing, argument parsing, help, and installed entry point.
2. `core/` - terminal primitives, bounded API reads, and process handling.
3. `state/` - paths, config IO, atomic writes, and preference mutations.
4. `services/` - AllAnime and AniList HTTP requests and normalization.
5. `domain/` - episodes, matching, titles, metadata, tracking, and history rules.
6. `media/` - source resolution, DASH, downloads, URLs, and local proxying.
7. `playback/` - mpv IPC, Android launching, runtime files, and completion rules.
8. `ui/` - cover helpers, fallback input, and reusable help content.
9. `app.py` - remaining stateful TUI orchestration and compatibility exports.

## Current Status

Completed boundaries:

- CLI parsing and package entry points
- terminal, process, API, config, and state IO helpers
- AniList and AllAnime request services
- episode, matching, metadata, title, tracking, sorting, and history rules
- source resolution, DASH, downloads, download-library scanning, and proxying
- mpv IPC/runtime handling and Android player launching
- cover validation/rendering helpers and non-TTY fallback input

Still intentionally in `app.py`:

- alternate-screen picker state and screen composition
- cover download coordination and redraw state
- local history cache orchestration
- AniList write queue and reconciliation orchestration
- the interactive application state machine

These areas share mutable session state. They should move behind explicit runtime
objects rather than importing or duplicating `app.py` globals.

## Rules

- Keep `allmanga-cli` executable throughout the migration.
- Preserve public function names used by tests until their callers are migrated.
- Do not combine feature changes with extraction commits.
- Run focused tests and the full AllManga suite after every extraction.
- Use Git commits instead of creating new whole-script backup folders.
- Keep `backups/` as read-only historical evidence and exclude it from Git.
