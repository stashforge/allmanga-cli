# Modularization Plan

The `allmanga-cli` executable remains the user-facing entry point. Runtime
behavior is moved incrementally into the `allmanga_cli` package, one tested
boundary per commit.

## Extraction Order

1. `cli_args.py` - command routing, argument parsing, and help formatting.
2. `terminal.py` - terminal sanitization, display width, truncation, and TTY IO.
3. `config.py` - config paths, validation, secure reads, and atomic writes.
4. `anilist.py` - AniList HTTP, cache, mutations, matching, and sync state.
5. `episodes.py` - episode catalog, provider numbering, and index navigation.
6. `streams.py` - source decoding, mirror resolution, DASH/HLS, and validation.
7. `playback.py` - players, local proxy lifecycle, resume, and completion rules.
8. `history.py` - local history persistence, filtering, and refresh behavior.
9. `covers.py` - cover cache, downloads, rendering, and generation control.
10. `tui.py` - pickers, menus, layouts, navigation, and screen rendering.

## Rules

- Keep `allmanga-cli` executable throughout the migration.
- Preserve public function names used by tests until their callers are migrated.
- Do not combine feature changes with extraction commits.
- Run focused tests and the full AllManga suite after every extraction.
- Use Git commits instead of creating new whole-script backup folders.
- Keep `backups/` as read-only historical evidence and exclude it from Git.
