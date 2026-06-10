---
name: csv_transform
content_shape: structured-csv
reference_tokens_per_char: 0.38
description: Transform a CSV and output CSV only, with no prose preamble.
---

[session-metrics:compare-suite:v2:prompt=csv_transform]

Take the CSV below and output a new CSV with two columns: `customer` and `total_usd`. `total_usd` is `sum(amount_cents) / 100` rounded to 2 decimals for each customer. The first row must be the header `customer,total_usd`. Sort by `total_usd` descending. Output ONLY CSV — no code fences, no preamble, no trailing commentary.

---

```
order_id,customer,amount_cents
1001,acme,1299
1002,beta,499
1003,acme,2000
1004,gamma,350
1005,beta,1299
1006,acme,750
1007,gamma,2000
```

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    import csv as _csv, io as _io
    s = text.strip()
    # Reject common preamble patterns.
    lower = s.lower()
    for pre in ("here", "sure", "i'll", "certainly", "```"):
        if lower.startswith(pre):
            return False
    try:
        rows = list(_csv.reader(_io.StringIO(s)))
    except Exception:
        return False
    if not rows or rows[0] != ["customer", "total_usd"]:
        return False
    # Each data row: two columns, second parses as float.
    for r in rows[1:]:
        if len(r) != 2: return False
        try: float(r[1])
        except ValueError: return False
    return len(rows) >= 2
````
