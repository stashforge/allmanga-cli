# Next Session Audit

Audit date: 2026-06-20

Scope: static scan of the current split `allmanga_cli` package. This is a
handoff document for the next work session, not a complete security audit.
Commands used included `find`, `rg`, targeted file reads, and package metadata
inspection. Live provider, player, Termux, and AniList mutation tests were not
performed during this pass.

## Current Baseline

- Package metadata is now correct: `pyproject.toml` defines the
  `allmanga-cli` package and `allmanga-cli` entry point.
- Source is split under `allmanga_cli/`, but core logic is still concentrated
  in large files.
- Tests exist and are useful: 35 test files and about 220 test functions.
- No `TODO`, `FIXME`, `XXX`, or `HACK` markers were found.
- No `shell=True`, `eval`, `exec`, `pickle`, or `os.system` usage was found.
- Subprocess calls are list-based, which is the right default.
- Local stream proxy binds to `127.0.0.1` and uses random path secrets.
- Token masking and `auth token --raw` exist, so full token display is explicit.

## Open First Next Session

Use this order if limit is low:

1. Fix watching/source reliability first.
2. Fix AniList sync correctness next.
3. Fix privacy/security gaps after watching is stable.
4. Continue splitting only after the active behavior is covered.

## Must Fix For Watching

### WATCH-01: Server extraction still needs live verification

Files:

- `allmanga_cli/media/resolver.py`
- `allmanga_cli/media/sources.py`
- `allmanga_cli/media/dash.py`
- `allmanga_cli/services/allanime.py`

Why:

- AllAnime source shape changes often.
- Earlier manual tests showed cases where `Yt-MP4` and `Mp4` existed in
  another client but this CLI only surfaced broken `Ok` streams or no streams.
- `--print-url` and source selection were reported as unreliable before the
  latest split work.

Next steps:

- Add one diagnostic command or debug mode that prints sanitized source names,
  decrypted source type, selected extractor path, and failure reason.
- Verify source priority with a known title, for example
  `Doupo Cangqiong: Nian Fan`.
- Keep preferred order focused on working sources: `Yt-MP4`, direct/default
  WixMP, Ak/DASH raw URLs, then other extractors.
- Do not log complete signed URLs by default.

### WATCH-02: `--print-url` needs a regression test

Files:

- `allmanga_cli/app/playback.py`
- `allmanga_cli/media/resolver.py`
- `allmanga_cli/cli/args.py`

Why:

- This command is useful for debugging and external players.
- It also exposes signed URLs, so behavior should be intentional and tested.

Next steps:

- Add tests for direct mp4, HLS, DASH video+audio, and no-stream cases.
- Normal output may print the selected URL because the flag is explicit.
- Debug logs should redact signed query strings.

### WATCH-03: Episode direct-play flow needs end-to-end checks

Files:

- `allmanga_cli/app/search.py`
- `allmanga_cli/app/details.py`
- `allmanga_cli/app/playback.py`
- `allmanga_cli/domain/episodes.py`

Why:

- `-e <episode>` should play directly when the episode exists.
- It should enter the episode page with a short footer message when the episode
  does not exist.
- Sparse and decimal episode IDs make this easy to regress.

Next steps:

- Test contiguous, sparse, missing, decimal, and string episode IDs.
- Keep all next/previous/binge behavior based on episode index, not integer
  episode guesses.

## AniList Sync Correctness

### AL-01: Completed status must depend on provider status and known total

Files:

- `allmanga_cli/domain/tracking.py`
- `allmanga_cli/app/playback.py`
- `allmanga_cli/app/details.py`
- `allmanga_cli/app_core.py`

Rule:

- Only set AniList status to `COMPLETED` when the show is actually finished
  and total episode count is known and reached.
- If a show is `RELEASING` or `NOT_YET_RELEASED`, never mark it completed just
  because all currently available episodes were watched.

Why:

- Ongoing anime with unknown total episodes were previously marked completed
  after all released episodes were watched.

Next steps:

- Add unit tests around releasing, not-yet-released, finished-known-total, and
  finished-unknown-total cases.
- Keep "watched all available" separate from "series completed".

### AL-02: Non-watching AniList statuses should move to watching on playback

Files:

- `allmanga_cli/domain/tracking.py`
- `allmanga_cli/app/playback.py`
- `allmanga_cli/app/details.py`

Rule:

- If user watches from `PLANNING`, `PAUSED`, or `DROPPED`, sync should move the
  entry to `CURRENT`.
- If user watches from `COMPLETED`, sync should move it to `REPEATING` unless
  this is a normal completed final update.
- If all episodes are completed and the provider is finished, sync to
  `COMPLETED`.

Next steps:

- Add behavior tests for manual "mark watched", natural completion, and binge.

### AL-03: Start and complete dates should be written carefully

Files:

- `allmanga_cli/app_core.py`
- `allmanga_cli/state/anilist_queue.py`
- `allmanga_cli/services/anilist.py`

Current notes:

- Queue records already have `started_at` and `completed_at` fields.
- Need verify mutation behavior against AniList and ensure existing dates are
  not overwritten unnecessarily.

Rules:

- Set start date only when newly starting and AniList has no start date.
- Set complete date only when moving to completed and AniList has no complete
  date.
- Offline queue should preserve date fields.

## Security And Privacy

### SEC-01: Plaintext token fallback is acceptable but needs clearer policy

Files:

- `allmanga_cli/state/secrets.py`
- `allmanga_cli/state/config.py`
- `allmanga_cli/app_core.py`

Current good parts:

- `secret-tool` keyring support exists.
- Config files are written under `~/.config/allmanga-cli/config.json`.
- Config permissions are set to `0600`; config directory is set to `0700`.
- `auth status` masks tokens.
- `auth token --raw` is the only intended full-token reveal.

Remaining risk:

- If keyring is unavailable, the token is stored in the private config file.
  That is okay for Termux and simple systems, but it is still plaintext.

Next steps:

- Document this clearly in `README` or `docs/security.md`.
- Add `auth migrate` or `auth login --force-keyring` later if useful.
- Add tests that `auth status`, `auth login`, debug logs, and crashes never
  print full tokens.

### SEC-02: Signed stream URLs should be redacted in logs

Files:

- `allmanga_cli/app_core.py`
- `allmanga_cli/media/resolver.py`
- `allmanga_cli/media/download.py`

Current good parts:

- JWT-like AniList tokens are redacted by `redact_sensitive_text`.
- Authorization bearer headers are redacted.

Remaining risk:

- Stream URLs can contain temporary signed query parameters.
- Exceptions, diagnostics, and `--debug` output may include those URLs.

Next steps:

- Extend redaction to hide query strings for known media URLs:
  `https://host/path?<redacted>`.
- Keep `--print-url` raw because that is explicit user intent.
- Avoid writing live source diagnostics with raw signed URLs into docs.

### SEC-03: Incognito should be audited across every write path

Files:

- `allmanga_cli/app/search.py`
- `allmanga_cli/app/anilist.py`
- `allmanga_cli/app/playback.py`
- `allmanga_cli/ui/covers.py`
- `allmanga_cli/ui/poster.py`
- `allmanga_cli/state/io.py`

Known good parts:

- Config and AniList queue writes check incognito in key paths.
- Playback history updates are guarded in playback code.

Questions to verify:

- Does incognito still write cover cache files?
- Does incognito still update search history?
- Does incognito still write logs on crash?
- Does incognito leave local proxy URLs in any persisted state?

Next steps:

- Add an incognito integration test with temp state/config directories.
- Assert no history, search history, playback, queue, or cover cache writes.
- Decide whether crash logs are allowed in incognito or require confirmation.

### SEC-04: Local proxy design is good, but keep it tested

Files:

- `allmanga_cli/media/local_proxy.py`
- `allmanga_cli/media/proxy_rules.py`
- `allmanga_cli/playback/android.py`

Current good parts:

- Binds to `127.0.0.1`.
- Uses random secret paths.
- Allows only GET and HEAD.
- Filters hop-by-hop and unsafe forwarded headers.
- Validates upstream HTTP(S) URLs and redirects.

Next steps:

- Add tests for wrong path, wrong method, bad Range, and filtered headers.
- Consider rejecting private-network upstream URLs unless explicitly needed.

## Stability And UX

### UX-01: Terminal image lifecycle is still fragile

Files:

- `allmanga_cli/ui/picker.py`
- `allmanga_cli/ui/poster.py`
- `allmanga_cli/ui/covers.py`

Why:

- There were multiple regressions with covers leaking into help screens,
  wrong screen row accounting, image redraw delay, and Termux resize behavior.

Next steps:

- Add a small terminal-image lifecycle abstraction:
  `show_cover`, `hide_cover`, `invalidate_cover`, `redraw_cover`.
- Add manual checklist for desktop and Termux:
  resize terminal, open keyboard, open help, close help, go back, refresh.

### UX-02: Picker layout needs resize handling

Files:

- `allmanga_cli/ui/picker.py`
- `allmanga_cli/ui/picker_render.py`

Why:

- User reported terminal resize and Termux keyboard open/close do not adapt
  immediately.

Next steps:

- Handle `SIGWINCH` or poll terminal size each frame.
- Clear/re-render cover when size changes.
- Keep footer fixed to bottom with blank placeholders.

### UX-03: History deletion needs Termux-friendly keys

Files:

- `allmanga_cli/app/search.py`
- `allmanga_cli/ui/help.py`
- `allmanga_cli/ui/picker.py`

Why:

- `Delete` key is not available on many Termux keyboards.

Next steps:

- Keep `Del`.
- Add `Ctrl+D` or a menu action with confirmation.
- Footer hint: `Del/Ctrl+D delete`.

### UX-04: Help pages and footer shortcut docs need a full pass

Files:

- `allmanga_cli/ui/help.py`
- `allmanga_cli/app/search.py`
- `allmanga_cli/app/anilist.py`
- `allmanga_cli/app/details.py`

Why:

- Shortcut hints changed often: Tab/Ctrl+N, Shift+Tab/Ctrl+P, Ctrl+R, R,
  Left/Esc behavior, delete confirmation.

Next steps:

- Make one shortcut registry per screen.
- Render footer hints and help page from the same data.

## Clean Code And Refactor Targets

### CLEAN-01: `app_core.py` is still too large

Current size:

- `allmanga_cli/app_core.py`: 3331 lines.

Good next splits:

- `auth.py`: token storage/status/login/token output.
- `anilist_sync.py`: queue, retry, mutations, date updates.
- `history_store.py`: load/save/patch/filter history.
- `playback_state.py`: resume time, pending completion, stream prefs.
- `formatting.py`: footer/status/action feedback strings.

Do not split by copy-paste only. Move focused groups with tests and keep public
wrappers if needed.

### CLEAN-02: UI picker is doing too many jobs

Current size:

- `allmanga_cli/ui/picker.py`: 697 lines.

Responsibilities currently mixed:

- input handling
- filtering
- help overlay
- cover rendering
- row accounting
- disabled rows
- non-TTY fallback
- status/footer rendering

Next steps:

- Extract input normalization.
- Extract cover lifecycle.
- Keep row rendering in `picker_render.py`.
- Add tests for parent/back behavior and disabled headers.

### CLEAN-03: AniList page should be split by feature

Current size:

- `allmanga_cli/app/anilist.py`: 729 lines.

Good split:

- `anilist_lists.py`
- `anilist_search.py`
- `anilist_airing.py`
- `anilist_sorting_ui.py`

Reason:

- Airing page is now a real feature and should not make list browsing harder to
  maintain.

### CLEAN-04: Use typed models gradually

Current issue:

- AllAnime data, AniList data, local history fields, UI-only fields, and sync
  fields share mutable dictionaries.

Next targets:

- `Stream`
- `EpisodeCatalog`
- `HistoryEntry`
- `AniListProgress`
- `AiringEntry`

Keep external provider responses as dictionaries at the boundary, then convert
to internal structures.

## Tests To Add First

1. AniList status transition tests:
   - planning -> current when watched
   - paused -> current when watched
   - completed -> repeating when rewatching
   - releasing + all available watched does not complete
   - finished + total reached completes
2. Source resolver tests:
   - Yt-MP4 decrypted clock path
   - WixMP/direct mp4 path
   - Ak/DASH rawUrls path
   - broken Ok/Filemoon path returns typed failure
3. Incognito write-boundary test:
   - no history/search/playback/queue writes
4. Terminal UI tests:
   - help does not keep cover
   - cover redraws after help
   - resize invalidates layout
   - footer stays bottom when no rows match
5. Auth safety tests:
   - full token appears only in `auth token --raw`
   - status/login/crash redaction keep token hidden

## Future Features

### FEAT-01: Airing page improvements

Current:

- `anilist airing` exists.
- Tabs: Today, Tomorrow, Next 5 Days.
- In-list schedule only.

Possible next:

- Filter by AniList list status.
- Show "already released but not watched" section.
- Jump from airing row to details without rematching when IDs are known.
- Optional all-season schedule later via public source, not token.

### FEAT-02: Data management commands

Useful commands:

- `data clear history`
- `data clear searches`
- `data clear covers`
- `data clear logs`
- `data export`
- `data import`

Reason:

- History, searches, logs, and covers are privacy-sensitive.

### FEAT-03: Doctor command

Useful checks:

- Python version
- mpv/mpvex/vlc availability
- yt-dlp availability
- ffmpeg availability
- chafa availability
- secret-tool/keyring availability
- config/state permissions
- terminal image support hint

## Keep These Good Patterns

- Keep subprocess calls list-based.
- Keep local proxy on `127.0.0.1`.
- Keep random proxy path secrets.
- Keep token raw output isolated under `auth token --raw`.
- Keep atomic JSON writes.
- Keep tests around pure domain helpers.
- Keep source URL validation before player/downloader calls.
- Keep local watching and AniList watching conceptually isolated.

## Quick Commands For Next Session

```bash
cd /home/tiru/projects/codex/allmanga-cli
git status --short
python3 -m compileall -q allmanga_cli
python3 -W error -m unittest discover -s tests -p 'test_allmanga_cli_*.py'
python -m allmanga_cli --help
python -m allmanga_cli auth status
```

For source debugging:

```bash
python -m allmanga_cli search "Doupo Cangqiong: Nian Fan" -e 203 --sources --debug
python -m allmanga_cli search "Doupo Cangqiong: Nian Fan" -e 203 --print-url --debug
```
