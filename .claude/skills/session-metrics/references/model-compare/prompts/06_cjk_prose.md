---
name: cjk_prose
content_shape: cjk-prose
reference_tokens_per_char: 0.95
description: Translate a short Japanese paragraph to English. Serves as a near-zero-delta control — CJK is roughly 1 token per character in both tokenizers.
---

[session-metrics:compare-suite:v2:prompt=cjk_prose]

Translate the following Japanese paragraph into natural English prose. Output the English translation only — no preamble, no romaji, no Japanese text in the output.

---

雨がようやく止むと、街角の古い街灯がちらちらと点き、濡れた石畳を薄黄色に照らした。毛並みの濡れた小さな犬が通りを小走りに過ぎていき、時折通る車にも見向きもしない。二階のパン屋の窓からは、小麦粉まみれのエプロンを着た女が外を眺めていた。片手を窓枠に置き、もう片方の手には、とっくに冷めてしまった青い欠けたカップを持っていた。朝には商人や配達トラックで賑わうこの界隈も、今この時間には、ただ雨だけのものになったように見えた。

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    # No CJK codepoints should remain in a correct English translation.
    for ch in text:
        cp = ord(ch)
        # Hiragana, Katakana, CJK Unified Ideographs (common + extension A).
        if 0x3040 <= cp <= 0x30FF: return False
        if 0x3400 <= cp <= 0x4DBF: return False
        if 0x4E00 <= cp <= 0x9FFF: return False
    return bool(text.strip())
````
