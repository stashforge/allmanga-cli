# allmanga-cli Project Review

Audit date: 2026-06-06

Scope: static review of the 5,669-line `allmanga-cli` snapshot from backup 094,
confirmed byte-for-byte identical to the active script. Compilation and `--help`
passed. Live provider, AniList mutation, Termux, download, and player tests were
not performed.

## Files

- `correctness_reliability.md`: bugs, races, data-loss risks, and failure handling.
- `security_privacy.md`: credential, network, local-process, and privacy risks.
- `maintainability_testing.md`: architecture, test gaps, and project hygiene.
- `must_have_features.md`: prioritized work required for a dependable release.
- `good_to_have_features.md`: useful improvements after the must-have work.
- `positive_controls.md`: practices already implemented correctly.

## Recommended Order

1. Add real version control and tests for the active script.
2. Fix mirror-generation races and make AniList writes durable.
3. Make matching and episode catalogs fail closed.
4. Secure temporary files, TLS, poster handling, and terminal output.
5. Add network timeouts and distinguish errors from empty results.
6. Split the script into modules only after behavior is covered by tests.

Finding IDs are stable references for future one-by-one fixes.
