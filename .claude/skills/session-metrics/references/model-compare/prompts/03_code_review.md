---
name: code_review
content_shape: code-review-diff
reference_tokens_per_char: 0.26
description: Review a Python diff and list issues as an unordered list with exactly three items.
---

[session-metrics:compare-suite:v2:prompt=code_review]

Review the Python diff below. Output your findings as a Markdown unordered list (lines starting with `- `) with EXACTLY three items. No preamble, no closing remarks, no headings — just the three bullet points. Each item should name a concrete issue in one sentence.

---

```diff
diff --git a/payments/refund.py b/payments/refund.py
@@
-def process_refund(payment_id, amount=None):
-    payment = db.query(f"SELECT * FROM payments WHERE id = '{payment_id}'").one()
-    if amount is None:
-        amount = payment.amount
-    if amount > payment.amount:
-        raise ValueError("refund exceeds payment")
-    refund = Refund(payment_id=payment_id, amount=amount)
-    db.session.add(refund)
-    db.session.commit()
-    try:
-        gateway.issue_refund(payment.gateway_ref, amount)
-    except Exception as e:
-        pass
-    return refund
+def process_refund(payment_id: str, amount: float | None = None) -> Refund:
+    payment = db.query(Payment).filter_by(id=payment_id).one()
+    refund_amount = amount if amount is not None else payment.amount
+    if refund_amount > payment.amount:
+        raise ValueError("refund exceeds payment")
+    with db.session.begin():
+        refund = Refund(payment_id=payment_id, amount=refund_amount)
+        db.session.add(refund)
+        gateway.issue_refund(payment.gateway_ref, refund_amount)
+    return refund
```

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    # Exactly three Markdown bullet items (- or *), no numbered lists.
    bullets = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            bullets += 1
    return bullets == 3
````
