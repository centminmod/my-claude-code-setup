---
name: tool_heavy_task
content_shape: agentic-tool-use
reference_tokens_per_char: 0.27
description: Force at least three tool calls. No predicate — the value is measuring tool-fanout ratio, not text compliance.
---

[session-metrics:compare-suite:v2:prompt=tool_heavy_task]

Use your Read tool to read each of these three files in turn (they are in your current working directory), then reconcile what you see across them into a single one-paragraph summary of the Meridian project's testing strategy:

1. `compare-fixture-unit-tests.md`
2. `compare-fixture-integration-tests.md`
3. `compare-fixture-release-checks.md`

You must actually invoke the Read tool three separate times — one per file — before writing the summary. Output the summary as one paragraph after the reads are complete.

<!-- PREDICATE -->

````python
# No predicate — tool fan-out is what we're measuring here, not the
# text output. The paired-turn ratio columns (token + cost) carry the
# signal; a check() that tested text would give misleading pass/fail.
check = None
````
