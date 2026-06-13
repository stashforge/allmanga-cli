# Must-Have Work

These are release-quality requirements, not optional polish.

## P0: Integrity And Safety

1. **Real version control**
   Initialize a Git repository, establish the current script as the baseline,
   and retain existing backup folders as migration evidence.

2. **Private runtime directory**
   Replace fixed `/tmp` mpv socket/config paths with unique private paths and
   deterministic cleanup. Resolves SEC-01.

3. **Generation-safe mirror resolution**
   Cancel or isolate stale resolver workers so streams cannot cross episode
   boundaries. Resolves COR-01.

4. **Durable AniList mutation queue**
   Completed in backup `106-durable-anilist-mutation-queue`: pending writes are
   persisted, retried, ordered, confirmed before cleanup, and flushed on exit.

5. **Fail-closed title matching**
   Completed in backup `112-fail-closed-title-matching`: automatic matches
   require title evidence, reject contradictory metadata, and require a clear
   confidence margin. Ambiguous results use the manual picker.

6. **Authoritative episode catalog**
   Completed in backup `114-authoritative-episode-catalog`: provider IDs are
   preserved exactly, catalog failures are explicit, legacy contiguous caches
   are labeled, and missing mappings fail closed.

7. **Core automated test suite**
   Cover episode movement, matching, history/sync reconciliation, navigation,
   and storage before structural changes.

## P1: Network And Privacy

8. **Central HTTP client**
   Add timeouts, response limits, typed errors, GraphQL error handling, retries,
   and rate-limit feedback.

9. **Secure media and cover fetching**
   Verify TLS, validate URL schemes, cap cover size, sanitize content, and apply
   subprocess timeouts.

10. **Terminal text sanitization**
    Sanitize every provider-controlled string before output.

11. **Secret-safe authentication**
    Hide token input, support keyring/separate token storage, and provide token
    revocation/logout guidance.

12. **Actual played-time tracking**
    Completed in backup `116-active-played-time-completion`: desktop mpv tracks
    active unpaused/non-buffering seconds and requires duration-relative watch
    time before automatic completion.

13. **Data management commands**
    Add clear/export/import for search history, watch history, resumes, links,
    cache, and logs; include no-history/private mode.

14. **Complete `--incognito` session mode**
    Completed in backup `135-incognito-mode`. Incognito:
    - force AniList sync off without changing the saved per-title preference
    - skip watch history, resume positions, pending completion, and checkpoints
    - skip search-history and manual-link writes
    - avoid persistent cover/search caches, or use a temporary session cache
    - avoid normal diagnostic logs unless an explicit debug override is requested
    - leave existing history and preferences untouched
    - show a clear `INCOGNITO` indicator in playback and menu metadata

## P2: Sustainable Structure

15. **Versioned state schemas and migrations**
16. **Module split with typed models**
17. **Structured private logging with redaction**
18. **Package metadata, version command, and reproducible installation**

The module split should begin after focused tests cover stream resolution,
episode catalogs, progress reconciliation, and navigation. Start with pure
helpers/models and storage; extract player/TUI/state-machine code last.
