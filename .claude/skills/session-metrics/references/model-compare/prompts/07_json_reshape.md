---
name: json_reshape
content_shape: structured-json
reference_tokens_per_char: 0.35
description: Reshape a JSON sample per a rubric, outputting valid JSON only.
---

[session-metrics:compare-suite:v2:prompt=json_reshape]

Reshape the JSON below so that:

1. The top-level is an array (not an object).
2. Each element has exactly three keys: `id`, `name`, `total_cents`.
3. `total_cents` is the sum of `line_items[*].cents` for that record (integer).

Output ONLY valid JSON. No code fences, no preamble, no trailing commentary. The output must parse cleanly with `json.loads()`.

---

```
{
  "orders": {
    "o_001": {
      "customer": "Acme Corp",
      "line_items": [
        {"sku": "widget-a", "cents": 1299},
        {"sku": "widget-b", "cents": 499},
        {"sku": "bundle-c", "cents": 2000}
      ]
    },
    "o_002": {
      "customer": "Beta LLC",
      "line_items": [
        {"sku": "widget-a", "cents": 1299}
      ]
    },
    "o_003": {
      "customer": "Gamma Inc",
      "line_items": [
        {"sku": "bundle-c", "cents": 2000},
        {"sku": "addon-x", "cents": 350}
      ]
    }
  }
}
```

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    import json as _json
    s = text.strip()
    # Strip an accidental ```json code fence if the model wrapped it.
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines)
    try:
        parsed = _json.loads(s)
    except Exception:
        return False
    if not isinstance(parsed, list):
        return False
    for item in parsed:
        if not isinstance(item, dict): return False
        if set(item.keys()) != {"id", "name", "total_cents"}: return False
        if not isinstance(item["total_cents"], int): return False
    return True
````
