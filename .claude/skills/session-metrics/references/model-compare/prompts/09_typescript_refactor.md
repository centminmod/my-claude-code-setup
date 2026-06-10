---
name: typescript_refactor
content_shape: code-refactor-ts
reference_tokens_per_char: 0.26
description: Refactor a TypeScript function for readability; must include the word "refactor" exactly twice.
---

[session-metrics:compare-suite:v2:prompt=typescript_refactor]

Refactor the TypeScript function below for readability (extract helpers, rename variables, simplify logic — anything that helps). Output the refactored code inside a single fenced ```ts code block, followed by a brief explanation paragraph.

CONSTRAINT: The total output MUST include the word `refactor` EXACTLY TWICE — no more, no fewer. Count case-insensitively. Choose your wording accordingly.

---

```ts
function doThing(x: any, opts: any) {
  let out: any = {};
  if (x && x.items && x.items.length > 0) {
    for (let i = 0; i < x.items.length; i++) {
      let it = x.items[i];
      if (it && it.status === "active" && (!opts || !opts.skipActive)) {
        if (!out[it.group]) out[it.group] = [];
        out[it.group].push({
          id: it.id,
          name: it.displayName || it.name || "unnamed",
          value: typeof it.value === "number" ? it.value : 0,
        });
      }
    }
  }
  return out;
}
```

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    return text.lower().count("refactor") == 2
````
