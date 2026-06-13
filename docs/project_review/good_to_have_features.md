# Good-To-Have Features

Implement these after the must-have integrity and security work.

## Playback And Tracking

- Configurable completion thresholds with sensible presets.
- Sync activity screen: pending, succeeded, failed, retry.
- Dry-run reconciliation showing local and AniList changes before applying.
- Per-title playback profile: sub/dub, quality, player, mirror, episode order.
- Better offline behavior using cached metadata and queued sync.
- Optional intro/outro skip integration when reliable metadata exists.

## Search And Library

- Filters for format, year, status, country, sub/dub, and airing state.
- Manual-link management screen to inspect, change, or remove saved mappings.
- Download library metadata index rather than relying only on filenames.
- Explicit mark/sync actions when playing downloaded files.
- Configurable history retention and archive view.
- Favorites/pinned titles independent of AniList.

## Diagnostics

- `--doctor` command for dependencies, permissions, TLS, API reachability,
  player IPC, and writable paths.
- `--version` and machine-readable diagnostics.
- Source reliability statistics and last failure reason.
- Exportable redacted debug bundle.
- Cache size display and cleanup controls.

## User Experience

- Color-disable and reduced-animation modes.
- Configurable key bindings.
- Better narrow-terminal layouts and accessibility-friendly status symbols.
- Explicit offline, timeout, authentication, and rate-limit messages.
- Confirmation for destructive history/link/cache operations.

## Distribution

- Installable Python package and standalone release artifact.
- Shell completions and man page.
- Release notes generated from fix IDs/backups.
- CI-tested Linux and Termux support matrix.
