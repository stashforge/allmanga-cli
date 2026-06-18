# Package Architecture

Runtime starts from the package entry point. Installed executions use the
`allmanga-cli` console script declared in `pyproject.toml`; source-tree runs use
`python -m allmanga_cli`.

## Ownership

- `allmanga_cli/cli`: argument parsing, help, and process entry points
- `allmanga_cli/core`: generic terminal, HTTP-decoding, and process utilities
- `allmanga_cli/domain`: pure anime, episode, history, matching, and tracking rules
- `allmanga_cli/media`: stream extraction, DASH, downloads, URLs, and proxy servers
- `allmanga_cli/playback`: player-specific runtime and IPC behavior
- `allmanga_cli/services`: remote AllAnime and AniList clients
- `allmanga_cli/state`: config, paths, atomic persistence, and preference mutations
- `allmanga_cli/ui`: reusable picker fallback, help, and cover rendering helpers
- `allmanga_cli/app.py`: compatibility imports for older tests and callers

## Dependency Direction

`core` and `domain` do not depend on the application. Services and media use
those lower-level modules. Playback and UI use services/media helpers. The
application composes every subsystem and owns mutable session state.

New provider logic belongs in `services` or `media`, not in `app_core.py`. New pure
formatting or decision rules belong in `domain`. Only navigation and shared
interactive state should remain in the application layer.
