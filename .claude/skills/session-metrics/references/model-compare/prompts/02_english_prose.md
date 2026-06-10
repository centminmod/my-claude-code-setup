---
name: english_prose
content_shape: english-prose
reference_tokens_per_char: 0.28
description: Rewrite a paragraph of English prose with no commas anywhere in the output.
---

[session-metrics:compare-suite:v2:prompt=english_prose]

Rewrite the paragraph below so that it contains zero commas. You may restructure sentences and use other punctuation (periods, semicolons, em-dashes, colons) but the output must contain no comma characters at all. Preserve the meaning. Output only the rewritten paragraph — no preamble, no trailing commentary.

---

When the rain finally stopped, the old streetlamp at the corner of Oak and Grant flickered on, casting a pale, yellow glow across the wet cobblestones, which shimmered in the evening air. A small dog, its coat matted and damp, trotted past, paying no attention to the occasional car, its paws making soft, wet slaps against the stone. From the upstairs window of the corner bakery, a woman in a flour-dusted apron watched, one hand resting on the sill, the other holding a chipped, blue cup of coffee that had long since gone cold. The neighborhood, so alive in the mornings with shouting merchants and delivery trucks, seemed, at this hour, to belong entirely to the rain.

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    return "," not in text
````
