---
name: claudemd_summarise
content_shape: prose-dense-claudemd
reference_tokens_per_char: 0.23
description: Summarise a CLAUDE.md-shaped doc in exactly 120 words.
---

[session-metrics:compare-suite:v2:prompt=claudemd_summarise]

Summarise the following project CLAUDE.md in EXACTLY 120 words. Do not write more or fewer. No headings, no lists — one continuous paragraph.

---

# Acme Billing Service — CLAUDE.md

## Overview

The Acme Billing Service is a Go-based microservice that handles invoice generation, payment reconciliation, and dunning workflows for roughly 40,000 active B2B customers. It runs on Kubernetes in three regions (us-east-1, eu-west-1, ap-southeast-2) with active-active multi-region Postgres via Aurora Global Database. Monthly GMV processed: ~$180M.

## Architecture highlights

- REST API on port 8080, gRPC on 9090 for internal services.
- Write path goes through a Kafka topic (`billing.events.v3`) with idempotency keys derived from `(tenant_id, external_ref, version)`.
- Read path is Postgres-backed with a write-through cache in Redis Cluster (6 nodes). Cache keys are namespaced by tenant and TTL'd at 5 minutes.
- All scheduled work runs via Temporal workflows — never plain cron. If you see a cron file, it's legacy and scheduled for removal.

## Common pitfalls

- **Idempotency is non-negotiable.** Every write endpoint must accept an `Idempotency-Key` header; duplicates return the original response with 200, never 409.
- **Tenant isolation is enforced at the DB layer** via row-level security. Do not bypass RLS even for admin tools — use the `billing_admin` role which has `SET ROW_SECURITY = on` enforced.
- **Don't add new top-level Kafka topics.** We're consolidating on `billing.events.v3`; add a discriminator column instead.
- **Reconciliation jobs must be idempotent and resumable.** Use Temporal's `ContinueAsNew` for long-running jobs.

## Testing

- Unit tests: `go test ./...` — must pass locally before PR.
- Integration tests: require `docker-compose up -d` for Postgres + Kafka + Redis + Temporal. Run with `make test-integration`.
- Contract tests against downstream services live under `tests/contracts/`; update them when the external shape changes, never on internal refactors.
- CI runs all three suites on every PR.

## Deployment

Canary rollout is 1% → 5% → 25% → 100% over 30 minutes per region, with SLO guards that auto-rollback on error-rate >0.5% or p99 latency >400ms for two consecutive 1-minute windows. Deploy via `./scripts/deploy.sh <env>`.

<!-- PREDICATE -->

````python
def check(text: str) -> bool:
    # Strict word-count check — IFEval-style.
    words = text.split()
    return len(words) == 120
````
