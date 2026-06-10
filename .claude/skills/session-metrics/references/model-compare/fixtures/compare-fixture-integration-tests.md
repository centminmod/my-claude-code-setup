# Integration testing notes — Meridian project

<!-- session-metrics compare-suite fixture. FROZEN CONTENT: this file is
     staged into the compare-run scratch directory and read by the
     tool_heavy_task prompt. Its byte size feeds cross-run token
     comparability — do not edit without bumping the compare-suite
     sentinel version. -->

Integration tests exercise the full pipeline against golden input
bundles checked into the repo: each bundle pairs a captured raw input
with the exact report it must produce, byte-for-byte. Golden files are
regenerated only by a dedicated script that prints a diff for human
review before overwriting. The suite runs on every commit; a separate
nightly job replays the ten largest historical bundles to catch
performance regressions, with a wall-clock budget per bundle.
