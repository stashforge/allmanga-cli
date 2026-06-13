# Correctness And Reliability Findings

## High Priority

### COR-01: Mirror resolver threads can mix episodes

Resolved in backup `105-generation-safe-mirror-resolution`.

Each stream-list reset and resolver start now advances a generation ID.
Background workers capture their generation and may publish streams or update
loading statistics only while it remains current. A stale worker exits after
an episode switch or replacement resolver run, even if it was blocked.

### COR-02: AniList writes can be lost on exit

Resolved in backup `106-durable-anilist-mutation-queue`.

Automatic progress mutations are persisted before network I/O, processed by
one ordered worker, retried on the next eligible run, and removed only after
AniList confirms success. Normal shutdown waits for queued work with a bounded
timeout; unfinished records remain durable.

### COR-03: Pending completion is cleared before sync succeeds

Resolved in backup `106-durable-anilist-mutation-queue`.

Pending completion and its resume position remain until the durable mutation
is confirmed. The queue record carries the completion marker across restarts,
including when a newer progress mutation supersedes the older record.

### COR-04: Automatic title matching can confidently choose the wrong anime

Resolved in backup `112-fail-closed-title-matching`.

Automatic matching now requires title similarity, rejects contradictory
season/year/type/episode metadata, and requires a confidence margin over the
second candidate. A single search result is scored normally rather than
accepted automatically. Common variations such as `Season 4`/`4th Season` and
joined/spaced romanization remain supported; ambiguous matches fall back to
manual selection.

### COR-05: Episode catalog failures are converted into plausible fake data

Resolved in backup `114-authoritative-episode-catalog`.

Episode catalogs now have explicit `loaded`, `unavailable`, and
`legacy_contiguous` states. Provider failures and GraphQL errors no longer
create or cache `1..N`. Sparse, decimal, and non-contiguous provider IDs are
preserved exactly. Unknown IDs and out-of-range progress no longer guess or
clamp to another episode; playback entry points show an unavailable/missing
catalog error instead.

### COR-06: AniList calls have no explicit timeout (Timeout resolved)

The missing-timeout issue was resolved in backup
`100-anilist-request-timeouts`. All six AniList request paths now use one
certificate-verifying helper with a 15-second timeout.

Remaining improvement: bounded retries, rate-limit handling, and clear typed
timeout/error feedback instead of returning empty results.

## Medium Priority

### COR-07: Completion is inferred from seek position, not watched time

Resolved in backup `116-active-played-time-completion`.

Desktop mpv sessions now accumulate active wall-clock playback only after
playback starts and while neither paused nor buffering. Completion requires
both an ending position and meaningful active playback: 25% of duration for
short episodes, capped at five minutes. EOF uses the same safeguard. Seeking
near the end and quitting no longer marks an episode watched.

### COR-08: Network failures are presented as empty search results

Resolved for search and manual-match flows in backup
`131-search-failure-feedback`.

AllAnime and AniList searches can now raise a sanitized `SearchFailure`, while
one-shot UI wrappers carry errors separately from result lists. Genuine empty
results still display as empty; timeout, connectivity, authentication/access,
rate-limit, server, HTTP, GraphQL, and invalid-response failures display their
actual category on the search input screen.

Remaining network improvement: retries, backoff, and typed failures for
non-search API operations.

### COR-09: Timed-out yt-dlp resolver processes are not terminated (Resolved)

Resolved in backup `098-ytdlp-timeout-cleanup`.

The resolver now terminates and reaps a timed-out process, escalating to kill
only when graceful termination also times out. Focused tests cover all paths.

### COR-10: Android proxy servers are never shut down

Resolved in backup `117-managed-android-proxy-lifecycle`.

The CLI now owns at most one Android stream proxy. A new launch closes the
previous proxy, direct-stream playback closes any obsolete proxy, failed
Android launches close the new proxy immediately, and process exit performs
deterministic shutdown and socket cleanup. Successful launches retain the
proxy because Android activities consume it asynchronously.

### COR-11: History silently discards older entries

Both watch and search history are truncated to `HISTORY_MAX = 50`
(`allmanga-cli:1488`, `1681`, `2045`).

Impact: old watch records disappear without warning or archive.

Fix direction: make retention configurable and provide archive/export or an
explicit pruning policy.

### COR-12: AniList search cache is not account-specific

Resolved in backup `120-account-scoped-anilist-cache`.

AniList list and search caches now include a SHA-256 fingerprint of the active
token. Different accounts and anonymous searches use separate namespaces, while
the token itself is never retained in a cache key.

### COR-13: Responses and images have no size limits

Cover downloads gained an 8 MiB streaming limit in backup
`103-secure-cover-downloads`. Provider and AniList API JSON responses gained an
8 MiB limit in backup `121-bounded-api-json-responses`. yt-dlp extractor JSON
output gained an 8 MiB incremental limit in backup
`129-bounded-ytdlp-json-output`.

Declared oversized responses are rejected before reading. Responses without a
valid Content-Length are read only through the limit plus one byte.
Oversized extractor output kills and reaps yt-dlp before decoding.

### COR-14: Non-TTY fallback cannot support search-input pickers

Resolved in backup `130-non-tty-search-fallback`.

Search and manual-match pickers now use line input when `/dev/tty` is
unavailable. Prefilled manual-match titles can be accepted with Enter, EOF
cancels cleanly, and empty non-search option sets fail closed instead of
displaying `Choose (1-0)`. The alternate screen is not activated before the
TTY check.

## Resolved UI Regression

### TUI-01: Cover redraws could scroll, overlap, and duplicate rows

Resolved in backup `107-deterministic-cover-layout` and refined in
`108-native-cover-container`.

The picker reserved eight rows but accepted terminal-dependent native image
geometry, then emitted an additional cursor-jump row into an already full-height
layout. Long final rows could also trigger terminal autowrap. The final design
reserves an eight-row text container and overlays native Chafa output at its
origin, preserving image quality without allowing image escape data to affect
row accounting. Final TUI lines remain width-limited.

### TUI-02: Filtered result headers could collapse from five rows to two

Resolved in backup `108-native-cover-container`.

When a local filter had no visible matches, the header callback had no selected
index and returned only its footer. Dynamic headers now reserve four rows, and
search results explicitly return three blank info rows plus the footer. With
the prompt/divider row, the bottom panel remains five rows.

### TUI-03: Restored cover margin caused a one-row frame overflow

Resolved in backup `109-exact-picker-row-accounting`.

The historical layout subtracted a poster margin from available result rows but
did not render it. Restoring the margin without also subtracting it from padding
made the frame one row taller than the terminal, scrolling divider fragments
into the first info row. Padding now includes every fixed zone, and each frame
line is written to an absolute terminal row.

### TUI-04: Loading and zero-match headers lacked context

Resolved in backup `110-corrected-ui-baseline-search-context`.

The search header now prioritizes loading context regardless of partial result
availability and receives the active local filter query from the picker.
Loading shows history navigation and source; a zero-match filter shows the
typed filter and source without collapsing the fixed header.
