# Security And Privacy Findings

## High Priority

### SEC-01: Predictable temporary mpv files allow local attacks (Resolved)

Resolved in backup `102-private-mpv-runtime`.

Each mpv session now receives a unique private runtime directory. The directory
is mode `0700`, the input config is created exclusively with mode `0600`, and
the socket/config directory is removed after playback and at process exit.

### SEC-02: TLS verification is disabled for stream probes and covers

`SSL_CTX` disables hostname and certificate verification
for stream probes. Cover TLS verification was fixed in backup
`103-secure-cover-downloads`. AniList, provider API, and cover requests now use
the certificate-verifying context.

Remaining impact: a network attacker can still replace stream content during
the compatibility probe path.

Remaining fix direction: verify stream TLS by default. If a specific CDN is
incompatible, require an explicit per-host fallback with a visible warning.

### SEC-03: Remote text can inject terminal control sequences (Resolved)

Resolved in backup `104-terminal-text-sanitization`.

Shared display boundaries now remove CSI/ANSI, OSC, DCS-style terminal strings,
C0/C1 controls, and embedded newlines from provider-controlled titles, mirror
names, query labels, status messages, and errors. Sanitization occurs before
the application adds its own trusted ANSI styling.

### SEC-04: Untrusted cover files are fed to complex image parsers (Resolved)

Resolved in backup `103-secure-cover-downloads`.

Cover requests now verify TLS, permit only credential-free HTTP(S) URLs, enforce
an 8 MiB limit, validate common image signatures, and use bounded decoder/chafa
execution. Unsupported or oversized data is rejected before parsing.

## Medium Priority

### SEC-05: AniList token remains plaintext at rest

The token is stored in JSON. The config is correctly mode `0600` on this system,
which limits exposure. Token entry was changed to hidden `getpass` input in
backup 097.

Remaining fix direction: support an OS keyring or separate `0600` token
file/environment variable while retaining file storage as an explicit fallback.

### SEC-06: URL schemes and destinations are not validated

Resolved in backups `103-secure-cover-downloads` and
`123-stream-url-validation`.

Cover, provider stream, embed, extractor-output, player, and download URLs now
require credential-free HTTP(S) and reject control characters. Stream probes,
`yt-dlp`, mpv, Android players, and downloads all enforce the policy before
receiving a destination.

Remaining optional hardening: constrain sensitive direct fetches by host class
to reduce exposure to HTTP(S) loopback or private-network destinations.

### SEC-07: Local stream proxy has no access token

Resolved in backups `117-managed-android-proxy-lifecycle` and
`118-hardened-android-proxy`.

The loopback proxy now uses a random per-launch path secret, accepts only GET
and HEAD, validates Range syntax, removes unsafe forwarded and hop-by-hop
headers, validates HTTP(S) upstream URLs and redirects, and applies a bounded
upstream timeout. Proxy ownership and cleanup remain limited to one active
server.

### SEC-08: Debug logs are written to the current directory (Resolved)

Resolved in backup `099-private-crash-logs`.

Crash and background logs now use atomic writes under the private state
directory. The log directory is mode `0700`, files are mode `0600`, and
filenames cannot escape the log directory.

Remaining improvement: redact signed URL query strings and rotate old logs.

### SEC-09: `--print-url` exposes signed media URLs

The command intentionally prints stream URLs and referers
(`allmanga-cli:5213-5219`). Terminal scrollback, shell capture, or support logs
can retain temporary credentials.

Fix direction: document this privacy property and add a redacted mode.

### SEC-10: Viewing and search history are sensitive local data

History, searches, resumes, manual links, and sync preferences are persisted.
Current files are mode `0600`, which is good, but there is no clear-history,
retention, export, or privacy-mode workflow.

Fix direction: add granular clear commands, configurable retention, and an
ephemeral/no-history mode.

## Privacy Disclosure Needed

Document that queries, title IDs, IP address, and playback requests may be sent
to AllAnime, AniList, cover CDNs, stream hosts, and yt-dlp-supported extractors.
AniList synchronization additionally sends account-linked progress and status.
