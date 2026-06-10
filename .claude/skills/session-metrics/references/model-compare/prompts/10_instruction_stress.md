---
name: instruction_stress
content_shape: instruction-stacked
reference_tokens_per_char: 0.25
description: IFEval-style stacked constraints — exactly 50 words, no commas, "foo" appears exactly twice, all lowercase.
---

[session-metrics:compare-suite:v2:prompt=instruction_stress]

Write a short description of a fictional coffee shop. The description MUST satisfy ALL of the following constraints simultaneously:

1. EXACTLY 50 words.
2. ZERO commas in the output.
3. The word `foo` appears EXACTLY TWICE.
4. All characters lowercase (no capital letters anywhere).

Output only the description — no preamble, no trailing commentary.

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    if "," in text: return False
    if text != text.lower(): return False
    words = text.split()
    if len(words) != 50: return False
    # Count occurrences of "foo" as a standalone word (case-insensitive).
    foo_count = sum(1 for w in words if w.strip(".!?:;-") == "foo")
    return foo_count == 2
````
