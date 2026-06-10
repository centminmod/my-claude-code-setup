# Release verification notes — Meridian project

<!-- session-metrics compare-suite fixture. FROZEN CONTENT: this file is
     staged into the compare-run scratch directory and read by the
     tool_heavy_task prompt. Its byte size feeds cross-run token
     comparability — do not edit without bumping the compare-suite
     sentinel version. -->

Before tagging a release, a drift-guard suite cross-checks every
user-facing constant (version strings, rate tables, format defaults)
against the documentation that quotes them, failing the build on any
mismatch. A smoke script then installs the packaged artefact into a
clean temp environment and runs three end-to-end invocations, asserting
exit codes and output-file presence only — depth lives in the unit and
integration layers, not here. No release ships with a skipped or
quarantined test on the manifest.
