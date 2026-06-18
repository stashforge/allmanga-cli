# allmanga-cli Fix Progress

This file tracks the one-by-one fixes applied to `allmanga-cli`. Each completed fix
has a matching backup folder under `backups/`.

## Current Count

No active items remain from the original fix list.

## Completed Areas

| Area | Backup folders |
|---|---|
| Crash fixes, stderr/debug cleanup, and safer background state | 001, 002, 009, 011, 022 |
| Stream/proxy/player reliability | 003, 008, 015, 021 |
| Real episode IDs and index-based episode movement | 061 |
| AniList progress mapping for decimal episode IDs | 064 |
| Cover cache, poster layout, cover loading status, native-image clearing, and nested-menu cover cleanup | 004, 006, 013, 042, 053, 054 |
| Search/matching speed, shared search UI helpers, bidirectional AniList matching, manual linking, direct linked-title reload, linked-title display, search result caching, and manual-match no-results feedback | 007, 043, 052, 053, 055, 058, 059, 060, 092, 093 |
| Config, token file permissions, SSL, and atomic state writes | 010, 014, 034, 035, 036, 038, 039 |
| AniList status, tracking, unified local history, checkpoint reconciliation, per-title sync, compact authority-aware history rows, manual completion progress, rewatch completion, filtered history, history details/navigation, sync-aware Details actions, manual mark actions, and pending player-next completion | 016, 018, 019, 020, 023, 024, 025, 026, 027, 028, 029, 030, 031, 037, 065, 081, 082, 083, 084, 085, 086, 087, 088, 089, 090 |
| Download success handling, configurable download directory, and downloaded-library browse/play mode | 032, 033, 066 |
| Message cleanup, Ctrl+C exit, display-width truncation/wrapping, redraw cleanup, menu label cleanup, hint truncation, and consistent parent-aware Left/Esc navigation | 040, 041, 044, 046, 047, 048, 050, 056, 062, 063, 091, 094 |
| Runtime state cleanup helpers for UI/navigation context | 067 |
| Removed stale Android binge watcher code | 045 |

## Remaining Active Fixes

- None.

## Full Audit Baseline

Static review completed in backup `095-full-project-audit`.

- Correctness and reliability findings
- Security and privacy findings
- Maintainability and testing findings
- Prioritized must-have work
- Good-to-have feature roadmap
- Positive controls that should be preserved

The detailed files are under `project_review/`. The first implementation
priorities are version control/tests, mirror worker isolation, durable AniList
writes, fail-closed matching, and authoritative episode catalogs.

## Workspace Cleanup

Completed in backup `096-workspace-cleanup`.

- Removed the superseded pre-audit review document.
- Removed the obsolete crash log for the already-fixed TTY descriptor failure.
- Removed generated Python bytecode and `__pycache__` directories.
- Preserved the active script, project review, separate `axcli` project, tests,
  project metadata, and every numbered source backup.

## Security Fix: Hidden AniList Token Input

Implemented in backup `097-hidden-anilist-token-input`.

- Both AniList authentication paths now use one `getpass` helper.
- Pasted tokens are no longer echoed into terminal output or scrollback.
- Existing atomic `0600` config storage remains unchanged.

## Stability Fix: yt-dlp Timeout Cleanup

Implemented in backup `098-ytdlp-timeout-cleanup`.

- Timed-out resolver processes are terminated and reaped.
- Processes that ignore termination are killed and reaped.
- Timeout messages are distinct from other yt-dlp failures.
- Added focused tests for success, terminate, and kill paths.

## Security Fix: Private Crash Logs

Implemented in backup `099-private-crash-logs`.

- Crash and background logs moved from the launch directory to
  `~/.local/state/allmanga-cli/logs/`.
- Log directory permissions are forced to `0700`.
- Log file permissions are forced to `0600`.
- Writes are atomic and filenames cannot escape the private log directory.
- Added focused path and permission tests.

## Stability Fix: AniList Request Timeouts

Implemented in backup `100-anilist-request-timeouts`.

- All six AniList request paths use one shared HTTP helper.
- AniList TLS certificate verification remains enabled.
- Every AniList request now has an explicit 15-second timeout.
- Added tests for the helper policy and complete call-site coverage.

## Security Fix: Private mpv Runtime

Implemented in backup `102-private-mpv-runtime`.

- Removed predictable shared `/tmp/allmanga-mpv.sock` and input config paths.
- Every mpv lifecycle uses a unique private runtime directory.
- Runtime directory permissions are `0700`; input config permissions are `0600`.
- Creation is lazy and cleanup runs after playback, startup failure, and process
  exit.
- Added focused uniqueness, permission, cleanup, and lazy-creation tests.

## Security Fix: Secure Cover Downloads

Implemented in backup `103-secure-cover-downloads`.

- Cover TLS certificate verification is enabled.
- Cover URLs must be credential-free HTTP(S).
- Downloads are streamed with an 8 MiB maximum.
- JPEG, PNG, GIF, WebP, and AVIF signatures are validated before parsing.
- ImageMagick, ffmpeg, and chafa calls have bounded execution time.
- Added focused URL, TLS, size-limit, and image-validation tests.

## Security Fix: Terminal Text Sanitization

Implemented in backup `104-terminal-text-sanitization`.

- Removes ANSI/CSI, OSC, DCS-style strings, C0/C1 controls, and embedded
  newlines from untrusted terminal text.
- Protects shared title, option, query, loading, mirror, status, and error
  display boundaries.
- Sanitization occurs before trusted application colors are added.
- Unicode titles remain intact.
- Added focused control-sequence and styling-preservation tests.

## Module Split Timing

Begin incremental extraction after focused tests cover stream resolution,
episode catalogs, sync reconciliation, and navigation. Extract pure helpers and
storage first; leave player, TUI, and the main state machine until last.

## Stability Fix: Generation-Safe Mirror Resolution

Implemented in backup `105-generation-safe-mirror-resolution`.

- Every stream-list reset and resolver start advances a generation.
- Background mirror workers stop when their generation becomes stale.
- Stream publication and resolver status updates verify the generation while
  holding the relevant lock.
- Starting a new episode no longer discards the old worker handle as a false
  substitute for cancellation.
- Regression tests cover an episode switch while an old resolver is blocked.

## Stability Fix: Durable AniList Mutation Queue

Implemented in backup `106-durable-anilist-mutation-queue`.

- Automatic playback progress is journaled before AniList network I/O.
- One worker preserves mutation order so older EP updates cannot finish after
  newer updates and regress remote progress.
- The latest queued state supersedes obsolete progress for the same title while
  retaining pending-completion cleanup metadata.
- Failed and interrupted writes remain in private state and retry on the next
  run where sync is enabled.
- Pending completion and resume state clear only after confirmed AniList sync.
- Normal exit performs a bounded flush; unfinished writes remain durable.
- Focused tests cover persistence, retry, ordering, coalescing, and completion
  cleanup.

## UI Fix: Deterministic Cover Layout And Redraw

Implemented in backup `107-deterministic-cover-layout`.

- Chafa cover output is forced to fixed-size symbol rows instead of native
  Kitty/Sixel/iTerm graphics with terminal-dependent geometry.
- Removed the extra absolute cursor-jump row that could scroll an otherwise
  full-height picker during every cover redraw.
- Poster output is padded or clipped to its reserved row count.
- Every final list, prompt, and info-panel row is width-limited before writing,
  preventing terminal autowrap from shifting the screen.
- Focused tests cover Chafa geometry flags and ANSI-aware line fitting.

## UI Fix: Native Cover Container And Fixed Info Panel

Implemented in backup `108-native-cover-container`.

- Restored Chafa's high-resolution native terminal output.
- The picker always reserves an eight-row invisible cover container.
- Native image data is overlaid at the container origin and is never counted
  as text rows, so it cannot move the list or info panel.
- Symbol output remains a fallback for terminals without a native protocol.
- Dynamic picker headers reserve four rows; together with the prompt/divider,
  search result screens keep the required five-row bottom panel.
- Search filtering with zero visible matches now emits three blank info rows
  plus the normal footer instead of collapsing the panel.

## UI Fix: Exact Picker Row Accounting

Implemented in backup `109-exact-picker-row-accounting`.

- Restored the intended visible one-row gap below the cover container.
- Corrected padding to subtract that gap, keeping the total frame exactly equal
  to terminal height instead of overflowing by one row.
- Picker rows are written with absolute row addresses rather than relying on
  cursor movement and CRLF behavior after native image output.
- Added an invariant test covering poster, margin, results, divider, and the
  fixed four-row info header.

## UI Fix: Corrected Baseline And Search Context

Implemented in backup `110-corrected-ui-baseline-search-context`.

- Replaced the workspace executable with the user-corrected
  `~/projects/agy/allmanga-cli` baseline.
- Preserved its alt-screen transition, cursor restoration, Chafa fallback, and
  search layout corrections.
- Search loading always shows history navigation and source lines, even after
  partial results arrive.
- The active local filter query is passed to result headers.
- Zero-match filtering shows `No match: <filter>` and `Source: <provider>`
  while retaining the original result-count footer.


## Privacy Feature: Incognito Mode

Implemented in backup `135-incognito-mode`.

- `--incognito` forces AniList sync off without changing saved title settings.
- Watch/search history, resumes, pending completion, checkpoints, manual links,
  config changes, and the durable AniList queue are not written.
- Existing resume positions are ignored for the private session.
- Covers use a private temporary cache that is removed at exit.
- Normal diagnostic logs are suppressed; `--debug` remains an explicit
  exception for troubleshooting.
- Persistent actions such as downloads, login, and logout cannot be combined
  with incognito mode.
- Details metadata and the playback screen show `INCOGNITO`.
- Focused tests verify untouched state, blocked network mutations, temporary
  cover storage, log policy, ignored resumes, and UI indication.

## CLI Structure: Initial Command Router

Implemented in backup `136-command-router`.

- Added command-oriented entry points for `search`, `download`, `downloads`,
  `anilist`, `history`, `continue`, and `auth`.
- Root help now lists available commands and examples.
- Every command has focused `--help` output containing only relevant options.
- Friendly AniList list names map to API statuses, including `watching`,
  `planning`, and `rewatching`.
- Existing bare-title searches and legacy flags such as `-a`, `-H`, `--login`,
  and `--download` remain supported unchanged.
- The router normalizes commands into the existing runtime argument fields, so
  playback and navigation behavior do not need duplicate command-specific code.
- Management commands will be added individually once their behavior exists.

## CLI Help: Command-First Layout

Implemented in backup `137-root-help-command-layout`.

- Removed the redundant `<command>` row from the command list.
- Root help now separates `Global options` and `Commands`.
- Legacy flags remain compatible but are no longer advertised in root help.
- Command-specific help remains unchanged and lists only valid options.

## CLI Help: Focused Command Documentation

Implemented in backup `138-command-specific-help`.

- `anilist` help now shows only friendly library lists and relevant output or
  global options.
- Internal aliases such as `current`, `repeating`, `plan-to-watch`, and `menu`
  remain accepted but are hidden from normal help.
- `anilist search` has its own parser and `--help` page.
- `search` options are grouped into playback, tracking, output, and global
  sections.
- `download` options are limited to download-relevant behavior and grouped by
  purpose.
- Each focused command includes examples at the bottom.
- Legacy AniList flags remain compatible.

## CLI Help: AniList Information Order

Implemented in backup `139-anilist-help-order`.

- AniList list names now appear immediately after the command description.
- Arguments and options follow the list reference.
- The optional `[list]` argument explains that omission opens the AniList menu.
- Incognito wording was shortened to `Do not save activity or update AniList`.

## CLI Help: Consistent Command Pages

Implemented in backup `140-consistent-command-help`.

- Standardized every current command help page to usage, description,
  command-specific reference, arguments, grouped options, and examples.
- Added focused help for `downloads`, `history`, `continue`, and `auth`.
- Grouped playback, tracking, output, and global options consistently.
- Auth actions are documented before the positional argument, matching AniList
  list documentation.
- Invalid AniList lists and auth actions now show their command-specific usage.

## CLI Help: Unified Usage And Color Style

Implemented in backup `141-unified-help-style`.

- Every current help page follows usage, description, command-specific
  reference or arguments, grouped options, and examples.
- Root help follows usage, description, commands, global options, and examples.
- Search and download use concise `<query> [options]` usage lines.
- Option descriptions align compactly on the same row where space permits.
- Replaced Python argparse's automatic coloring with a minimal TTY-only scheme:
  blue bold section headers, green option flags, and normal positional
  arguments, command names, descriptions, and examples.
- Piped help, `NO_COLOR`, and dumb terminals remain plain text.

## CLI Help: Compact Option Labels

Implemented in backup `142-clean-option-labels`.

- Removed value metavars such as `EPISODE`, `QUALITY`, and `PLAYER` from option
  rows.
- Kept accepted values and requirements in descriptions and examples.
- Option parsing and validation remain unchanged.
- Shorter labels allow descriptions to remain aligned on the same line.
A visible `INCOGNITO` indicator is required so the active privacy state is
unambiguous.

## Correctness Fix: Fail-Closed Title Matching

Implemented in backup `112-fail-closed-title-matching`.

- Automatic matches require a meaningful title similarity signal.
- A single search result is no longer accepted without scoring.
- Conflicting season, year, type, or episode metadata rejects a candidate.
- The best result must clear a confidence threshold and lead the runner-up.
- `Season 4`/`4th Season` and joined/spaced romanization remain supported.
- Ambiguous provider/AniList matches fall back to manual selection.
- Added focused matching tests for false matches, naming variations,
  contradictions, ambiguity, and clear winners.

## UX Fix: Single AniList Search Result

Implemented in backup `113-single-anilist-result-auto-select`.

- A single AniList search result opens automatically.
- The normal confidence-based AllAnime match runs immediately.
- Failed automatic matches fall back to the manual match picker.
- Canceling manual match returns to search instead of reopening in a loop.
- Left, Esc, and Back preserve direct-result navigation behavior.

## Correctness Fix: Authoritative Episode Catalog

Implemented in backup `114-authoritative-episode-catalog`.

- `availableEpisodesDetail` IDs remain authoritative, including gaps and
  decimal episode numbers.
- Catalog state is explicit: `loaded`, `unavailable`, or
  `legacy_contiguous`.
- API failures and GraphQL errors no longer fabricate or cache `1..N`.
- Unknown requested IDs no longer guess an episode index.
- Progress beyond the known catalog no longer clamps to the last episode.
- Playback, episode selection, history resume, and action menus fail closed
  when no reliable catalog exists.
- Added focused tests for sparse catalogs, decimals, empty success responses,
  failures, legacy data, unknown IDs, and progress overflow.

## History Fix: Highlighted AniList Refresh

Implemented in backup `115-history-anilist-highlight-refresh`.

- Highlighting an AniList-synced history row refreshes its account progress,
  list status, airing data, total episodes, score, titles, type, and dates.
- Refresh starts after a short debounce so fast scrolling does not issue API
  requests.
- Each synced title is refreshed once per history session.
- Footer status shows AniList refresh, success, or failure without blocking
  navigation.
- Refreshed rows and metadata are persisted to local history.
- Remote refresh does not overwrite the last reconciliation checkpoint, so
  local-vs-AniList conflicts remain detectable.
- Added focused tests for progress/status refresh, local-only exclusion, and
  history persistence.

## Playback Fix: Active Played-Time Completion

Implemented in backup `116-active-played-time-completion`.

- Desktop mpv reports active played seconds separately from playback position.
- Paused and buffering intervals are excluded.
- Seeking changes position but does not add watched time.
- Automatic completion requires an ending position plus 25% active playback,
  capped at five minutes for normal episodes.
- Short episodes use proportional thresholds, such as one minute for a
  four-minute episode.
- EOF uses the same played-time safeguard.
- Early seek-to-end during binge leaves pending completion for confirmation by
  the next episode instead of marking the previous episode watched.
- Explicit Mark as Watched actions remain immediate.

## Stability Fix: Managed Android Proxy Lifecycle

Implemented in backup `117-managed-android-proxy-lifecycle`.

- The CLI retains ownership of the proxy needed by asynchronous Android
  players.
- At most one local stream proxy remains active.
- Starting another Android stream closes the previous proxy.
- Direct streams close an obsolete header proxy.
- Failed Android launches close the newly created proxy immediately.
- CLI exit shuts down and closes the active proxy.
- Threaded request handlers are daemonized so abandoned client connections do
  not block server cleanup.

## Security Fix: Hardened Android Proxy

Implemented in backup `118-hardened-android-proxy`.

- Every proxy launch receives a random 128-bit path secret.
- Requests to any other path return 404 without contacting the stream host.
- Only GET and HEAD are accepted; other methods return 405.
- Range headers are forwarded only when they match valid byte-range syntax.
- Host, content length, control-containing, and hop-by-hop request headers are
  removed.
- Hop-by-hop response headers and headers named by `Connection` are removed.
- Upstream URLs and redirects must remain credential-free HTTP(S).
- Upstream requests use certificate verification and a bounded timeout.

## Playback UX Fix: Direction-Aware mpv Transitions

Implemented in backup `119-direction-aware-mpv-transition-osd`.

- Shift+Left now reports previous-episode loading, readiness, starting, and
  failure instead of using next-episode text.
- Shift+Right retains matching next-episode messages.
- Manual loading and starting OSD messages persist until playback replaces
  them or resolution fails.
- Ready and starting states are combined during an immediate transition so the
  user can see that resolution completed and playback is switching.
- Prefetch state now pairs direction with the requested episode index.
- A completed prefetch for the opposite direction cannot be reused for the
  current request.
- Added regression tests for message wording, persistent duration, and target
  matching.

## Correctness Fix: Account-Scoped AniList Cache

Implemented in backup `120-account-scoped-anilist-cache`.

- AniList list caches are scoped by account and requested status.
- AniList search caches are scoped by account and normalized query.
- Anonymous searches use their own namespace.
- Account scope uses a SHA-256 token fingerprint; raw tokens are never stored
  in cache keys.
- Switching accounts in one process cannot reuse another account's list
  progress or `mediaListEntry` state.

## Reliability Fix: Bounded API JSON Responses

Implemented in backup `121-bounded-api-json-responses`.

- Provider and AniList API JSON bodies are limited to 8 MiB.
- Oversized declared Content-Length values are rejected before body reads.
- Missing or invalid Content-Length responses are read only through the limit
  plus one detection byte.
- All shared provider and AniList JSON paths use the same bounded decoder.
- Video streams and proxy media bodies are not affected by this JSON limit.
- yt-dlp subprocess JSON output remains a separate future hardening item.

## Playback Fix: AniList Cover Loading

Implemented in backup `122-anilist-playback-cover`.

- The playback screen requests the cover for its active merged provider object.
- AniList-started playback no longer depends on poster state from the earlier
  AniList selection object.
- Existing cover caching, validation, Chafa rendering, and async loading remain
  shared with the rest of the TUI.

## Security Fix: Stream URL Validation

Implemented in backup `123-stream-url-validation`.

- Provider embed and direct-media destinations must be credential-free HTTP(S).
- Invalid URLs are rejected before probes or `yt-dlp` extraction.
- URLs returned by `yt-dlp` are validated before becoming playable streams.
- Desktop, Android, and download launch boundaries validate stream URLs again.
- Referer URLs are restricted to the same credential-free HTTP(S) policy.

## UI Fix: AniList Menu Layout And Loading Isolation

Implemented in backups `124-anilist-list-screen-layout` and
`125-anilist-direct-list-loading-screen`.

- AniList Lists restores its blank first info row and fixed five-row panel.
- Direct `-a <list>` loading enters the alternate screen before drawing status.
- Loading text no longer remains in the shell's primary screen buffer.
- Menu and direct-list paths share reusable layout/loading helpers.
- Direct `-a <list>` now renders the AniList Lists screen with the requested
  list highlighted while its data loads.
- Loading replaces only the footer row instead of appearing on a blank screen.

## Navigation Fix: AniList Menu Exit And Search

Implemented in backup `126-anilist-menu-navigation`.

- Selecting an AniList title no longer overwrites the AllAnime search query.
- Returning from title details and then leaving the list cannot auto-search the
  previously selected AniList title.
- `Esc` exits directly from AniList Lists.
- `Left` opens a fresh AllAnime search input with no pending query.

## Completed Feature: Per-Title AniList Sync

Implemented in backup `081-per-title-anilist-sync`.

- `-t, --sync` enables AniList sync for playback.
- `--no-sync` disables AniList sync for the current run.
- Anime Details can toggle persistent sync outside AniList-owned menus.
- Local and AniList playback histories are isolated.
- Automatic sync does not reduce normal AniList progress.
- Provider episode IDs remain real IDs for playback while AniList progress uses episode order.
- Synced titles use AniList names; local-only titles use source names.
- Compact metadata, hints, OSD, and status text use `EP`, `LOCAL`, and `AL`.

## Completed Feature: Unified Progress Reconciliation

Implemented in backup `087-unified-progress-reconciliation`.

- One local history remains the playback source of truth.
- Each history entry can store `last_synced_progress`.
- Sync On reconciles local and AniList progress before resume.
- Local-only changes push to AniList; AniList-only changes import locally.
- Normal two-sided changes use the higher progress.
- Rewatch two-sided changes expose explicit conflict resolution.
- AniList mode reads AniList first; `--no-sync` writes subsequent progress only
  to local history.
- `--sync` and `--no-sync` persist the title's sync preference.
- Metadata shows only one progress authority instead of simultaneous LOCAL and
  AL values.
- Explicit Rewatch resets both progress stores to EP 0 and changes AniList to
  `REPEATING`.

## UI Fix: Bottom-Aligned Empty Info Panels

Implemented in backup `127-bottom-aligned-info-panel`.

- Short picker headers are padded above their content instead of below it.
- A lone footer remains on the final info-panel row when filtering has no match.
- Existing complete four-row panels retain their exact row order.
- Empty rows remain empty instead of adding page-specific placeholder text.

## Feature: AniList List Sorting

Implemented in backup `128-anilist-list-sorting`.

- AniList lists default to `Recent`, combining local watch timestamps with
  AniList entry `updatedAt`.
- `Tab` cycles `Recent`, `AniList`, `Title`, and `Progress`.
- The active sort is shown in the list prompt and stored as `anilist_sort`.
- AniList's original API order is retained separately and can always be
  restored without mutating cached results.
- Stable ties preserve the original AniList order.

## Reliability Fix: Bounded yt-dlp JSON Output

Implemented in backup `129-bounded-ytdlp-json-output`.

- yt-dlp extractor stdout is read incrementally with an 8 MiB limit.
- Oversized output kills and reaps the extractor before JSON decoding.
- Stderr is discarded instead of accumulating beside JSON output.
- Existing timeout behavior still terminates, then kills if necessary.
- All stdout pipes are closed after success, overflow, or timeout.

## Reliability Fix: Non-TTY Search Input

Implemented in backup `130-non-tty-search-fallback`.

- Search and manual-match pickers accept normal line input without `/dev/tty`.
- Empty input accepts an existing prefilled manual-match query.
- EOF and interruption cancel instead of entering an infinite loop.
- Numbered non-TTY selection remains available for ordinary option lists.
- The alternate screen is entered only after a usable TTY is confirmed.

## Reliability Fix: Search Failure Feedback

Implemented in backup `131-search-failure-feedback`.

- Genuine empty searches remain distinct from network and API failures.
- AllAnime and AniList search UIs propagate sanitized typed failures.
- Timeout, connectivity, authentication/access, rate-limit, server, HTTP, and
  invalid-response failures receive specific messages.
- Manual AllAnime and AniList matching reuse the same feedback path.
- Successful and cached search result behavior remains unchanged.
- Automatic retries and rate-limit backoff remain separate future work.

## Feature: Ak DASH rawUrls Playback

Implemented in backup `132-ak-dash-rawurls`.

- Ak Clock `rawUrls` video and audio tracks are now resolved directly.
- AVC is preferred, duplicate resolutions are reduced to their best bitrate,
  and the best AAC track is paired with every selected video quality.
- Desktop mpv loads separate video and audio URLs.
- Android receives a locally served fixed-quality DASH MPD compatible with
  mpvEx, VLC, and Next Player.
- Ak downloads use ffmpeg to mux the separate tracks without re-encoding.
- Unsafe URLs and malformed MPD metadata are rejected or sanitized.
- The existing broken Ak subtitle endpoint remains excluded.

## Navigation Fix: Details Left Restores Search Results

Implemented in backup `133-details-left-restores-results`.

- Left from Details or the Episode picker preserves the active query after a
  multi-result selection, returning to the cached title-selection page.
- Direct single-result Left behavior and all Esc behavior remain unchanged.

## UI Feedback: Title Selection Loading

Implemented in backup `134-title-selection-loading-feedback`.

- Uncached episode-catalog requests show `Loading episode list...`.
- AniList-to-AllAnime matching shows `Matching title on AllAnime...`.
- Normal search, AniList search, and AniList list selection are covered.
- Cached transitions remain immediate without unnecessary loading flashes.

## Deferred Or Watch Items

- Continue package cleanup: the runtime is now split into `allmanga_cli`, but
  some stateful orchestration still lives in `app_core.py`.
- Full AppState refactor: the high-risk direct UI/navigation global access has been
  moved behind helpers, but a full object-based state refactor should wait until
  the CLI is manually stable.
- Hardcoded AniList client ID: leaving this hardcoded is better UX unless the client
  ID stops working.
- Parallel mirror probing: defer unless speed becomes more important than probe
  reliability.
- Downloaded-library tracking: downloads should not update watch history by
  themselves; local playback can get explicit mark/track behavior later.

## Verification Baseline

For each code fix:

- Run `python3 -m compileall allmanga_cli`.
- Run a light CLI smoke test such as `python3 -m allmanga_cli --help`.
- Run a targeted behavior check when the fix touches search, playback, AniList,
  downloads, covers, or history.
