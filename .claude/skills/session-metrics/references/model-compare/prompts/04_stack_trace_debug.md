---
name: stack_trace_debug
content_shape: stack-trace
reference_tokens_per_char: 0.30
description: Diagnose a Python stack trace in at most 200 output tokens (~800 chars).
---

[session-metrics:compare-suite:v2:prompt=stack_trace_debug]

Diagnose the root cause of the Python stack trace below in 200 OUTPUT TOKENS OR FEWER. Prefer one tight paragraph. State the cause, point at the offending call, and suggest the fix. No code blocks, no lists, no preamble.

---

```
Traceback (most recent call last):
  File "/app/workers/ingest.py", line 87, in process_batch
    for record in batch_iter(file_path, chunk_size=chunk):
  File "/app/workers/ingest.py", line 34, in batch_iter
    with gzip.open(path, "rt", encoding="utf-8") as fh:
  File "/usr/lib/python3.12/gzip.py", line 74, in open
    binary_file = GzipFile(filename, gz_mode, compresslevel)
  File "/usr/lib/python3.12/gzip.py", line 174, in __init__
    fileobj = self.myfileobj = builtins.open(filename, mode or 'rb')
FileNotFoundError: [Errno 2] No such file or directory: '/tmp/ingest/2026-04-19/batch_0042.json.gz'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/app/workers/ingest.py", line 132, in <module>
    main()
  File "/app/workers/ingest.py", line 128, in main
    process_batch(manifest_entry, chunk_size=CHUNK_SIZE)
  File "/app/workers/ingest.py", line 91, in process_batch
    metrics.record_failure(manifest_entry["id"])
KeyError: 'id'
```

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    # Approximate the 200-token budget by char length (~4 chars/token).
    # Allow a small margin for tokenizer variance.
    return 0 < len(text) <= 900
````
