# Unit testing notes — Meridian project

<!-- session-metrics compare-suite fixture. FROZEN CONTENT: this file is
     staged into the compare-run scratch directory and read by the
     tool_heavy_task prompt. Its byte size feeds cross-run token
     comparability — do not edit without bumping the compare-suite
     sentinel version. -->

Unit coverage targets the parsing layer first: every record type in the
ingest format has a dedicated round-trip test, and malformed-input cases
are enumerated in a table-driven suite rather than ad-hoc asserts. The
team standard is one test file per module, mirrored by filename. Mocks
are allowed only at process boundaries (clock, filesystem, subprocess);
everything in between runs real code. Coverage is measured but not
gated — the suite fails on behaviour, not on percentages.
