# Claude Model Pricing Reference

Prices in **USD per million tokens**. Snapshot: **2026-09-23** (every Anthropic
row re-verified against the rate card).
Source: https://platform.claude.com/docs/en/about-claude/pricing

Anthropic bills **two cache-write tiers**:

- **5-minute TTL** (`cache_write` column): **1.25× base input**
- **1-hour TTL** (`cache_write_1h` column): **2× base input**

As of **v1.2.0** the per-entry split is read from
`message.usage.cache_creation.ephemeral_{5m,1h}_input_tokens` when the
nested object is present. Legacy transcripts without that object fall
back to the 5-minute rate — preserves pre-v1.2.0 numbers for those
files.

**Cache read** (hits + refreshes) is **0.1× base input** regardless
of TTL.

## Current models

| Model ID                    | Alias      | Input | Output | Cache read | 5m Cache write | 1h Cache write |
|-----------------------------|------------|-------|--------|------------|----------------|----------------|
| `claude-opus-5-5`           | opus-5-5   |  4.00 |  20.00 |       0.20 |           5.00 |           8.00 |
| `claude-opus-5`             | opus-5     |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-opus-4-8`           | opus-4-8   |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-opus-4-7`           | opus-4-7   |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-opus-4-6`           | opus-4-6   |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-opus-4-5`           | opus-4-5   |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-sonnet-4-7`         | sonnet-4-7 |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-sonnet-4-6`         | sonnet-4-6 |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-sonnet-4-5`         | sonnet-4-5 |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-haiku-4-5-20251001` | haiku-4-5  |  1.00 |   5.00 |       0.10 |           1.25 |           2.00 |
| `claude-haiku-4-5`          | haiku-4-5  |  1.00 |   5.00 |       0.10 |           1.25 |           2.00 |
| `claude-fable-5-1`          | fable-5-1  | 10.00 |  50.00 |       0.25 |          12.50 |          20.00 |
| `claude-fable-5`            | fable-5    | 10.00 |  50.00 |       1.00 |          12.50 |          20.00 |
| `claude-sonnet-5` †         | sonnet-5   |  2.00 |  10.00 |       0.20 |           2.50 |           4.00 |

> **Important — pricing tier change at Opus 4.5**: Opus 4.5 / 4.6 / 4.7 / 4.8
> moved to a new cheaper tier ($5 input / $25 output). Opus 4 and 4.1 retain the
> original $15 / $75 tier. Earlier snapshots of this table had Opus 4.6/4.7
> at the old rates — corrected 2026-04-17.
>
> **1M-context variant**: when a session runs an Opus model at the 1M-context
> tier, Claude Code tags `message.model` with a `[1m]` suffix (e.g.
> `claude-opus-4-8[1m]`, `claude-opus-4-7[1m]`). These resolve to the same base
> rates as the bare model id via the prefix sweep — the >200K-context premium is
> not modelled (consistent across all Opus minors, not just 4.8). The
> bare-major future keys (`claude-opus-5` / `claude-sonnet-5` / `claude-haiku-5`,
> see below) likewise catch every `5.x` minor plus its `[1m]` and date-suffixed
> forms through the same prefix sweep.
>
> **Fable 5** (shipped 2026-06, Claude Code CLI first) is a new model family on
> its **own premium tier** ($10 input / $50 output) — distinct from Opus, Sonnet,
> and Haiku. `claude-fable-5` is a **bare-major** key, so it catches every `5.x`
> minor + `[1m]` + date suffix through the prefix sweep. Cache columns follow the
> standard ratios off the $10 base (read 0.1× = $1, 5m-write 1.25× = $12.50,
> 1h-write 2× = $20). A future un-keyed `claude-fable-6` routes to a dedicated
> family fallback at the Fable 5 tier (flagged), not to the Sonnet default.
>
> **Fable 5.1** (`claude-fable-5-1`, v1.88.0) keeps the $10/$50 tier and the
> Fable 5 cache-write rates but **cache reads dropped to $0.25** (0.025× base
> input — every other Anthropic model reads at 0.1×). It therefore has its own
> explicit key, listed before the bare-major `claude-fable-5` so the prefix
> sweep resolves its `[1m]` / date-suffixed forms to the $0.25 read rate.
> Claude Code stamps `message.model` as bare `claude-fable-5-1`, and the Fable
> family's **default** context window is 1M (no `[1m]` tag), which the
> session-health context-pressure signal now honours.
>
> **Opus 5.5** (`claude-opus-5-5`, v1.89.0) is **cheaper** than Opus 5:
> $4 / $20, cache writes $5 (5m) / $8 (1h), and **cache reads $0.20** (0.05×
> base input, not the usual 0.1×). It has its own key listed before the
> bare-major `claude-opus-5`, so `claude-opus-5-5` and its `[1m]` /
> date-suffixed forms no longer prefix-match the $5/$25 Opus 5 rate. Fast mode
> is $8 / $40 (2× standard), applied via `_FAST_MODE_MULTIPLIERS`.
>
> **Opus 5** (`claude-opus-5`, released 2026-07-24) shipped at the $5 / $25 tier
> the pre-provisioned bare-major key already assumed — verified against the
> Anthropic pricing page 2026-09-25 (v1.90.2), no rate change. Opus 5 and
> Opus 5.5 are **1M-context only**, and Claude Code stamps them bare (no
> `[1m]`), so `_MODEL_CONTEXT_WINDOWS` carries `claude-opus-5` at 1M for the
> session-health context-pressure signal (prefix covers `claude-opus-5-5`).
>
> **† Sonnet 5 standard is $2/$10 (v1.89.1)**: `claude-sonnet-5` launched at an
> "introductory" $2/$10 announced to run through 2026-08-31, with a scheduled rise
> to $3/$15 on 2026-09-01. Anthropic cancelled the rise: $2/$10 is now the
> standard price. v1.84.0–v1.89.0 priced Sonnet 5 turns dated 2026-09-01 or later
> at $3/$15 (a 50% over-count); v1.89.1 moves the flat entry to $2/$10 and drops
> the date window, so every Sonnet 5 turn prices at $2/$10 regardless of date.
> `audit-extract.py` carries a matching `claude-sonnet-5` row ($2), allow-listed
> in the drift guard's `ALLOWED_MAJOR_ONLY`.
>
> **Date-effective pricing** (`_PRICING_SCHEDULES` + `_pricing_for_at`) prices
> each turn at the rate in effect on its own UTC date, so reprocessing an old
> transcript stays correct. Current windows cover GPT-5.6 only (see the OpenAI
> section). A window applies to its key, the key's `[1m]` / date-suffixed forms,
> and any id that resolves to the key's flat entry (e.g. the bare `gpt-5.6-terra`
> slug). Turns with a missing / unparseable / timezone-naive timestamp use the
> flat entry.

## Effort support by model

Pricing is effort-independent (effort changes token *counts*, not rates),
but the compare/benchmark harnesses pass `--effort` rungs through to
headless `claude -p` runs, so the supported ladder per model matters
there. Verified against the Anthropic effort docs, 2026-06-11; Opus 5 row
added 2026-09-25
(https://platform.claude.com/docs/en/build-with-claude/effort):

| Model family            | Supported efforts                  | API default | Anthropic-recommended for coding/agentic |
|-------------------------|------------------------------------|-------------|------------------------------------------|
| `claude-opus-4-5` / `-4-6` | low / medium / high / max       | high        | high                                      |
| `claude-opus-4-7` / `-4-8` | low / medium / high / xhigh / max | high      | xhigh                                     |
| `claude-fable-5`        | low / medium / high / xhigh / max  | high        | high (xhigh only for the most capability-sensitive work) |
| `claude-fable-5-1`      | low / medium / high / xhigh / max  | high        | high (thinking always on; `disabled` is rejected)         |
| `claude-opus-5`         | low / medium / high / xhigh / max  | high        | high (xhigh for demanding coding/agentic; thinking can't be disabled at xhigh/max) |
| `claude-opus-5-5`       | low / medium / high / xhigh / max  | **medium**  | set explicitly (thinking always on; `disabled` is rejected) |
| `claude-sonnet-4-6`+    | low / medium / high / max          | high        | medium                                    |

Note: Opus 4.8's default is `high` on all surfaces including Claude
Code — `xhigh` is the *recommended* setting for coding, not the default.

## Future / pre-provisioned models

These keys were added **proactively** (v1.44.0) so the next wave of Anthropic
models is recognised the moment it ships — no spurious unknown-model warning and
no `[1m]` mispricing. Each uses its **family-current** rate (the tiers above).
**The rates are assumptions** — review each when the model actually ships, in
case Anthropic re-tiers a generation.

| Model ID         | Family rate | Notes |
|------------------|-------------|-------|
| `claude-opus-4-9`  | Opus new $5/$25   | exact + `[1m]`/date via prefix sweep |
| `claude-opus-5`    | Opus new $5/$25   | **bare-major** — catches all `5.x` minors + `[1m]`. Shipped 2026-07-24; rate verified 2026-09-25 (see Current models) |
| `claude-sonnet-4-8`| Sonnet $3/$15     | (`claude-sonnet-4-7` already shipped) |
| `claude-sonnet-4-9`| Sonnet $3/$15     | |
| `claude-haiku-4-6` | Haiku $1/$5       | |
| `claude-haiku-4-7` | Haiku $1/$5       | |
| `claude-haiku-4-8` | Haiku $1/$5       | |
| `claude-haiku-4-9` | Haiku $1/$5       | |
| `claude-haiku-5`   | Haiku $1/$5       | **bare-major** — catches all `5.x` minors + `[1m]` |

Anything *beyond* these keys (e.g. a hypothetical `claude-opus-6`) still falls to
the family-fallback regex: priced at the family tier **and** flagged in the
at-exit unknown-model advisory as a nudge to add an explicit key. As of v1.44.0
the fallback boundary also accepts the `[1m]` tag, so an un-keyed future
`[1m]` variant prices at its family tier instead of defaulting to Sonnet.

## Legacy / prefix-fallback entries

These entries are kept for historical JSONL files that reference older models,
and for prefix-matching fallback when a model ID isn't explicitly listed.

| Model ID (prefix match) | Input | Output | Cache read | 5m Cache write | 1h Cache write |
|-------------------------|-------|--------|------------|----------------|----------------|
| `claude-sonnet-4`       |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-3-7-sonnet`     |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-3-5-sonnet`     |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-3-5-haiku`      |  0.80 |   4.00 |       0.08 |           1.00 |           1.60 |
| `claude-3-opus`         | 15.00 |  75.00 |       1.50 |          18.75 |          30.00 |
| (default fallback)      |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |

> **Opus 4.0 / 4.1 (OLD $15/$75 tier) are NOT prefix entries** — they were
> removed from the prefix table (`claude-opus-4` in v1.41.2, `claude-opus-4-1`
> in v1.45.1) and are matched by **anchored regexes** in `_PRICING_PATTERNS`:
> `^claude-opus-4(?:-\d{8})?$` and `^claude-opus-4-1(?:-|\[|$)`. As plain prefix
> keys they silently caught their two-digit extensions (`claude-opus-4-N`,
> `claude-opus-4-10`..`-19`) and over-charged 3×. The anchored forms price only
> the exact IDs plus their date / `[1m]` suffixes at OLD-tier, leaving un-keyed
> future minors to the NEW-tier family fallback (with an unknown-model warning).

## Non-Anthropic models

These entries use OpenRouter as the pricing source of truth. Cache columns are
0 for most entries, but caching is NOT Claude-specific: `moonshotai/kimi-k3`
transcripts populate `cache_read_input_tokens` and OpenRouter bills K3 cache
reads at $0.30/M, so that entry carries a non-zero `cache_read` (cache-write
columns stay 0 — K3 transcripts show `cache_creation` always 0 and OpenRouter
charges no write premium). The GPT-5.6 family goes further: OpenRouter bills
both cache reads (0.1× input) and cache writes (1.25× input) for all six
GPT-5.6 IDs, so those entries carry non-zero `cache_read` AND `cache_write`
columns (one published write rate — no 5m/1h split — so both write columns
hold the same value). Since v1.90.0/v1.90.1 every GLM and DeepSeek V4 entry
also bills cache reads (no write premium).
The `gemma4` entry is a prefix fallback that covers Ollama local variants
(`gemma4-26b-32k`, `gemma4-26b-48k`, `gemma4:e4b`, etc.) at the Gemma 4 26B A4B
OpenRouter rate — a reasonable estimate for mixed-environment JSONL files.

Source: [OpenRouter pricing](https://openrouter.ai/pricing) — snapshot 2026-04-25;
GLM + DeepSeek V4 re-snapshotted 2026-09-23 from `https://openrouter.ai/api/v1/models`
(per-token `pricing.prompt` / `completion` / `input_cache_read`, × 1e6).

`_pricing_for` uses three tiers in order: **exact match → regex patterns
(`_PRICING_PATTERNS`) → prefix sweep**. Regex patterns sit before the prefix
sweep so families with shared prefixes (e.g. `glm-5` vs `glm-5-turbo`) resolve
correctly regardless of dict insertion order.

**Boundary policy (v1.41.0)**: numeric-suffix families (gpt-5.5, qwen3.6/3.7,
mimo-v2.5, kimi-k2.6/2.7, minimax-m2.7/m3) carry `(?!\d)` so a model with one
extra trailing digit (`gpt-5.55`, `qwen3.60-plus`) falls through to default
Sonnet rates instead of being mispriced as the shorter version. Provider /
model separators use the class `[-_/.]` (not bare `.`) so `deepseek.v4-flash`
keeps matching while `deepseekXv4Yflash` is correctly rejected. Suffix tokens
(`pro`, `flash`, `plus`) carry `\b` so they don't glue to longer words.

> ⚠️ **Behaviour change at v1.41.0**: model names that previously
> over-matched the looser regex (e.g. unknown `gpt-5.55-foo`) now route
> to default Sonnet rates instead of the shorter family's rates.
> Re-run reports for accurate before/after comparisons if you have
> historical sessions touching such IDs.

### GLM (Z.ai)

| Model ID                     | Input  | Output | Cache read | Regex pattern |
|------------------------------|--------|--------|------------|---------------|
| `glm-4.7`                    | 0.40   | 1.75   | 0.08       | `glm-4\.7`    |
| `glm-5`                      | 0.60   | 1.92   | 0.12       | `glm-5`       |
| `glm-5.1`                    | 0.966  | 3.036  | 0.1794     | `glm-5\.1`    |
| `glm-5.2`                    | 0.6496 | 2.0416 | 0.12064    | `glm-5\.2`    |
| `z-ai/glm-5.3-flash`         | 0.15   | 0.50   | 0.05       | `glm-5\.3(?!\d).*flash\b`  |
| `z-ai/glm-5.3-flashx`        | 0.37   | 1.25   | 0.075      | `glm-5\.3(?!\d).*flashx\b` |
| `z-ai/glm-5.3`               | 0.6538 | 2.0548 | 0.12142    | `glm-5\.3(?!\d)` (after the flash tiers) |
| `z-ai/glm-5-turbo`           | 1.20   | 4.00   | 0.24       | `glm-5-turbo` |

> **GLM re-snapshot (v1.90.1, OpenRouter `/api/v1/models`, 2026-09-23)**: every
> GLM entry now carries OpenRouter's current rate, including billed cache reads
> (no write premium). Previous values were the 2026-04-25 snapshot with cache
> reads recorded as $0. Every bare `glm-5.x` form has a guard that keeps it off
> the bare `glm-5` prefix. `flash\b` and `flashx\b` separate the two Flash
> SKUs, and the base `glm-5.3` pattern runs after both. Non-round figures
> (0.6496, 0.6538 …) are OpenRouter's provider-weighted prices, which drift.
> Re-snapshot rather than trust them long-term. Historical turns reprice at
> the current rate, because OpenRouter publishes no effective dates.

### Google Gemma 4

| Model ID                     | Input | Output | Note |
|------------------------------|-------|--------|------|
| `google/gemma-4-26b-a4b`     |  0.06 |   0.33 | Exact + prefix for `…a4b-it` variants |
| `gemma4`                     |  0.06 |   0.33 | Prefix for Ollama local variants |

### Qwen (Alibaba)

| Model ID                     | Input | Output | Regex pattern        |
|------------------------------|-------|--------|----------------------|
| `qwen3.5:9b`                 |  0.10 |   0.15 | exact                |
| `qwen/qwen3.6-plus`          | 0.325 |   1.95 | `qwen3\.6(?!\d).*plus\b` |
| `qwen/qwen3.7-plus`          |  0.32 |   1.28 | `qwen3\.7(?!\d).*plus\b` |

### OpenAI (via OpenRouter)

| Model ID                     | Input  | Output  | Regex pattern        |
|------------------------------|--------|---------|----------------------|
| `openai/gpt-5.5-pro`         | 30.00  |  180.00 | `gpt-5\.5(?!\d).*pro\b` |
| `openai/gpt-5.5`             |  5.00  |   30.00 | `gpt-5\.5(?!\d)`     |
| `openai/gpt-5.6-sol`         |  5.00  |   30.00 | `gpt-5\.6[-_/.]sol\b`   |
| `openai/gpt-5.6-terra`       |  2.00  |   12.00 | `gpt-5\.6[-_/.]terra\b` |
| `openai/gpt-5.6-luna`        |  0.20  |    1.20 | `gpt-5\.6[-_/.]luna\b`  |

> **GPT-5.6 date-effective rates (v1.89.1, verified against OpenAI's pricing
> page 2026-09-23)**. Flat rows above are the current standard rates. Windows:
>
> | Model | Window (UTC, half-open) | Input | Output | Cache read | Cache write |
> |---|---|---|---|---|---|
> | Terra | before 2026-07-30 (pre-cut) | 2.50 | 15.00 | 0.25 | 3.125 |
> | Luna  | before 2026-07-30 (pre-cut) | 1.00 |  6.00 | 0.10 | 1.25 |
> | Sol   | 2026-08-21 → 2026-11-22 (promo) | 4.00 | 20.00 | 0.40 | 5.00 |
>
> OpenAI cut Terra and Luna on 2026-07-30. The Sol promo started 2026-08-21 and
> is "available at least through November 21, 2026"; after that Sol turns
> revert to the $5/$30 standard. If OpenAI extends the promo, extend the
> window's `until`. Turns with no usable timestamp price at the flat row (Sol
> standard, never the promo).

> **GPT-5.6 family (snapshot 2026-07-18)**: three capability tiers — Sol,
> Terra, Luna. The official Codex CLI slugs are the bare tier names
> (`gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna`), which the tier regexes
> resolve identically to the `openai/`-prefixed OpenRouter IDs. OpenRouter's
> `-pro` siblings (`gpt-5.6-sol-pro` etc.) are priced identically to their
> base tier and intentionally share its regex; if OpenAI ever re-prices a pro
> variant it needs its own preceding pattern. All six IDs bill cache reads at
> 0.1× input and cache writes at 1.25× input — the first GPT entries with
> non-zero cache columns. An un-tiered `gpt-5.6` string (bare, or a future
> variant like `gpt-5.6-codex`) prices at the Terra tier via the family
> fallback **with** an unknown-model warning; `gpt-5.66`+ stays on default
> Sonnet rates per the standard digit-boundary policy.

### OpenAI GPT-6 (OpenAI API pricing, snapshot 2026-09-23)

| Model ID                     | Input  | Output  | Cache read | Cache write | Regex pattern          |
|------------------------------|--------|---------|------------|-------------|------------------------|
| `openai/gpt-6-astra`         | 10.00  |   50.00 |       1.00 |       12.50 | `gpt-6[-_/.]astra\b`   |
| `openai/gpt-6-sol`           |  2.00  |   10.00 |       0.20 |        2.50 | `gpt-6[-_/.]sol\b`     |
| `openai/gpt-6-luna`          |  0.10  |    0.50 |       0.01 |       0.125 | `gpt-6[-_/.]luna\b`    |

> **GPT-6 family (v1.89.0)**: three tiers — Astra (flagship), Sol, Luna.
> Source: https://developers.openai.com/api/docs/pricing. The regexes match
> both the bare slugs (`gpt-6-sol`) and `openai/`-prefixed IDs; GPT-6 Sol and
> GPT-5.6 Sol are distinct rates and never collide. One published cache-write
> rate, so both write columns carry it. OpenAI's long-context surcharge (2×
> input/cache, 1.5× output) is not modelled. There is no un-tiered fallback:
> a bare `gpt-6` prices at default Sonnet rates **with** an unknown-model
> warning.

### DeepSeek V4

| Model ID                          | Input    | Output   | Cache read | Regex pattern |
|-----------------------------------|----------|----------|------------|---------------|
| `deepseek/deepseek-v4-pro-0813`   | 0.66     | 1.98     | 0.022      | `deepseek[-_/.]v4[-_/.]pro[-_/.]0813\b`   |
| `deepseek/deepseek-v4-flash-0731` | 0.04     | 0.64     | 0.016      | `deepseek[-_/.]v4[-_/.]flash[-_/.]0731\b` |
| `deepseek/deepseek-v4.1-flash`    | 0.15     | 0.60     | 0.003      | `deepseek[-_/.]v4\.1(?!\d).*flash\b`      |
| `deepseek/deepseek-v4-pro`        | 0.899058 | 1.798116 | 0.074922   | `deepseek[-_/.]v4(?!\.\d)[-_/.].*pro\b`   |
| `deepseek/deepseek-v4-flash`      | 0.049    | 0.098    | 0.0098     | `deepseek[-_/.]v4(?!\.\d)[-_/.].*flash\b` |

> **Base V4 re-snapshot (v1.90.1, OpenRouter 2026-09-23)**: `v4-pro` and
> `v4-flash` were $1.74/$3.48 and $0.14/$0.28 with cache reads at $0
> (2026-04-25 snapshot). Both now carry OpenRouter's current rates, including
> billed cache reads. The `v4-pro` figure is provider-weighted and moved within
> an hour of the first read ($0.9008 → $0.899058), so expect drift.

> **DeepSeek snapshots + V4.1 (v1.90.0, OpenRouter 2026-09-23)**: the dated
> V4 snapshots and V4.1 Flash have their own rates. All three bill cache reads
> (0.022 / 0.016 / 0.003 per M, no write premium). Their patterns run before
> the generic V4 patterns, which used to swallow them at base-V4 rates. Because
> `.` is a separator, `deepseek-v4.1-flash` matched the V4 flash pattern. The
> generic V4 patterns now carry `(?!\.\d)`, so an un-keyed dotted minor (e.g. a
> future `v4.1-pro`) is flagged unknown instead of silently priced as V4.
> DeepSeek's own API bills peak / off-peak rates (off-peak = half of peak, by
> UTC hour) and serves floating aliases (`deepseek-flash`, `deepseek-v4-pro`).
> Neither is modelled; OpenRouter's flat per-model rate is the source of truth.

### Xiaomi MiMo V2.5

| Model ID                     | Input | Output | Regex pattern        |
|------------------------------|-------|--------|----------------------|
| `xiaomi/mimo-v2.5-pro`       |  1.00 |   3.00 | `mimo[-_/.]v2\.5(?!\d).*pro\b` |
| `xiaomi/mimo-v2.5`           |  0.40 |   2.00 | `mimo[-_/.]v2\.5(?!\d)`        |

### Moonshot Kimi

| Model ID                     | Input  | Output | Regex pattern |
|------------------------------|--------|--------|---------------|
| `moonshotai/kimi-k2.6`       | 0.7448 |  4.655 | `kimi[-_/.]k2\.6(?!\d)` |
| `moonshotai/kimi-k2.7-code`  |  0.75  |  3.50  | `kimi[-_/.]k2\.7(?!\d)` |
| `moonshotai/kimi-k3`         |  3.00  | 15.00  | `kimi[-_/.]k3(?!\d)` |

> **K3 cache reads**: unlike every other non-Anthropic entry, `kimi-k3` has
> `cache_read` = **0.30** $/M (live transcripts carry non-zero
> `cache_read_input_tokens`; OpenRouter publishes the rate — snapshot
> 2026-07-18 for this row). Cache-write columns remain 0. A future dotted
> minor (`kimi-k3.5`) would match the integer-version `k3` regex and needs its
> own preceding guard when it ships (same reactive policy as glm-5.1/5.2).

### MiniMax

| Model ID                     | Input | Output | Regex pattern      |
|------------------------------|-------|--------|--------------------|
| `minimax/minimax-m2.7`       |  0.30 |   1.20 | `minimax[-_/.]m2\.7(?!\d)` |
| `minimax/minimax-m3`         |  0.30 |   1.20 | `minimax[-_/.]m3(?!\d)` |

## Notes

- **Prefix fallback order matters**: dict insertion order is traversed until
  the first match. More-specific entries (e.g. `claude-opus-4-7`) must appear
  **before** less-specific ones (e.g. `claude-opus-4`), otherwise an unknown
  future Opus-4.7-* model ID would fall through to the old-tier rate.
- **5m vs 1h cache writes** (v1.2.0+): `_cost` splits
  `cache_creation_input_tokens` into its two ephemeral buckets using
  `message.usage.cache_creation.ephemeral_{5m,1h}_input_tokens` and charges
  each at the correct rate. Turns without the nested object (legacy
  transcripts) fall back to the 5-minute rate, preserving their prior cost.
- **Fast mode** (research preview, **Opus 4.6 / 4.7 / 4.8 / 5 / 5.5 only**): a
  premium rate tier — Opus 4.6/4.7 bill at **6× standard** ($30 input / $150
  output), Opus 4.8 and Opus 5 at **2×** ($10 / $50), Opus 5.5 at **2×** ($8 /
  $40). Prompt-caching multipliers apply *on top of*
  the fast base, so every token category scales by the same factor. **Applied
  since v1.64.0**: `_cost` / `_no_cache_cost` multiply the per-turn *primary*
  token cost by the per-model factor (`_FAST_MODE_MULTIPLIERS`) when
  `usage.speed == "fast"`. The advisor sub-cost is **not** scaled — it is a
  separate model invocation whose speed tier the iteration record doesn't
  carry. Pass `--no-fast-premium` to reproduce pre-v1.64.0 numbers. Source:
  Anthropic pricing § "Fast mode pricing".
- **Server-side web tools**: `web_search` is billed **$0.01 per request**
  ($10 / 1,000 searches), outside the token rate — added by `_cost` since
  v1.64.0, **after** any fast multiplier (a flat per-request charge is not
  tier-scaled). `web_fetch` carries **no per-request charge** (token-only), so
  it is intentionally not counted. Source: Anthropic pricing § "Web search
  tool" / "Web fetch tool".
- **Data residency multiplier**: US-only inference via `inference_geo`
  adds 1.1× on top of all rates (Opus 4.6+/Sonnet 4.6+/Haiku 4.5+). Not
  tracked — no non-empty values observed in any transcript.
- Prices are estimates; actual billing is on Anthropic's platform.
