# Positive Controls Already Present

These should be preserved during future fixes.

- AniList and provider API requests use a certificate-verifying SSL context.
- Every AniList request uses a shared explicit 15-second timeout.
- Provider and AniList JSON responses are capped at 8 MiB, including responses
  without a valid Content-Length.
- Config is written atomically and forced to mode `0600`.
- Current history, playback, search-history, and config files are mode `0600`.
- Crash and background logs are atomically written under a `0700` private log
  directory with file mode `0600`.
- mpv IPC and input configuration use a unique per-session `0700` runtime
  directory; the config is `0600` and cleanup is registered for process exit.
- JSON state writes use temporary files, `fsync`, and `os.replace`.
- Invalid JSON is moved aside instead of being overwritten immediately.
- Subprocesses use argument arrays; no `shell=True`, `eval`, or `exec` was found.
- Download filenames remove path separators and unsafe punctuation.
- Cover cache filenames are SHA-256-derived rather than URL-derived paths.
- Cover downloads verify TLS, require credential-free HTTP(S), cap data at
  8 MiB, validate image signatures, and bound decoder execution time.
- Cover rendering reserves a fixed cell container and overlays high-resolution
  native output without changing text row accounting. Final TUI rows are
  width-limited to prevent overlap, autowrap, and redraw scrolling.
- Provider-controlled terminal text is sanitized at shared title, list, query,
  mirror, loading, status, and error display boundaries.
- The Android proxy binds to loopback rather than all network interfaces.
- Android proxy ownership is bounded to one active server with deterministic
  replacement, failure, and process-exit cleanup.
- Android proxy URLs contain a random path secret and enforce GET/HEAD-only,
  bounded HTTP(S) forwarding with unsafe header filtering.
- Shared stream list operations use a lock.
- Background mirror workers are generation-scoped, so stale episode workers
  cannot publish streams or overwrite resolver status after navigation.
- Automatic AniList writes use a private durable journal, preserve submission
  order, retry after restart, and receive a bounded shutdown flush.
- AniList list and search caches are isolated by a non-reversible account
  fingerprint; raw tokens are not stored in cache keys.
- Poster object mutation and active-download tracking use locks.
- AniList links persist both provider ID and AniList ID.
- Automatic title matching requires title evidence, rejects contradictory
  metadata, and refuses ambiguous or low-confidence candidates.
- Real provider episode IDs are used when `availableEpisodesDetail` succeeds.
- Episode catalogs preserve gaps and decimal IDs, distinguish unavailable and
  legacy data, and never fabricate mappings after provider failures.
- AniList-synced history rows refresh account progress and status on highlight
  with debounce, stale-selection protection, and persistent local updates.
- Desktop completion uses active unpaused/non-buffering playback time, so
  seeking near the end cannot immediately mark an episode watched.
- Ctrl+C handling and terminal restoration have explicit paths.
- Stored token values were not observed in normal log or error formatting.
- The active script compiles and its `--help` command succeeds.

Some controls are incomplete rather than absent. For example, stream-list
locking prevents memory corruption but does not prevent stale episode workers;
loopback binding limits proxy exposure but does not authenticate local clients.
