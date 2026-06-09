# Claude Model Pricing Reference

Prices in **USD per million tokens**. Snapshot: **2026-04-18**.
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
| `claude-opus-4-8`           | opus-4-8   |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-opus-4-7`           | opus-4-7   |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-opus-4-6`           | opus-4-6   |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-opus-4-5`           | opus-4-5   |  5.00 |  25.00 |       0.50 |           6.25 |          10.00 |
| `claude-sonnet-4-7`         | sonnet-4-7 |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-sonnet-4-6`         | sonnet-4-6 |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-sonnet-4-5`         | sonnet-4-5 |  3.00 |  15.00 |       0.30 |           3.75 |           6.00 |
| `claude-haiku-4-5-20251001` | haiku-4-5  |  1.00 |   5.00 |       0.10 |           1.25 |           2.00 |
| `claude-haiku-4-5`          | haiku-4-5  |  1.00 |   5.00 |       0.10 |           1.25 |           2.00 |
| `claude-fable-5`            | fable-5    | 10.00 |  50.00 |       1.00 |          12.50 |          20.00 |

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

## Future / pre-provisioned models

These keys were added **proactively** (v1.44.0) so the next wave of Anthropic
models is recognised the moment it ships — no spurious unknown-model warning and
no `[1m]` mispricing. Each uses its **family-current** rate (the tiers above).
**The rates are assumptions** — review each when the model actually ships, in
case Anthropic re-tiers a generation.

| Model ID         | Family rate | Notes |
|------------------|-------------|-------|
| `claude-opus-4-9`  | Opus new $5/$25   | exact + `[1m]`/date via prefix sweep |
| `claude-opus-5`    | Opus new $5/$25   | **bare-major** — catches all `5.x` minors + `[1m]` |
| `claude-sonnet-4-8`| Sonnet $3/$15     | (`claude-sonnet-4-7` already shipped) |
| `claude-sonnet-4-9`| Sonnet $3/$15     | |
| `claude-sonnet-5`  | Sonnet $3/$15     | **bare-major** — Sonnet is single-tier across minors |
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
all 0 (prompt caching is Claude-specific and not charged for by OpenRouter).
The `gemma4` entry is a prefix fallback that covers Ollama local variants
(`gemma4-26b-32k`, `gemma4-26b-48k`, `gemma4:e4b`, etc.) at the Gemma 4 26B A4B
OpenRouter rate — a reasonable estimate for mixed-environment JSONL files.

Source: [OpenRouter pricing](https://openrouter.ai/pricing) — snapshot 2026-04-25.

`_pricing_for` uses three tiers in order: **exact match → regex patterns
(`_PRICING_PATTERNS`) → prefix sweep**. Regex patterns sit before the prefix
sweep so families with shared prefixes (e.g. `glm-5` vs `glm-5-turbo`) resolve
correctly regardless of dict insertion order.

**Boundary policy (v1.41.0)**: numeric-suffix families (gpt-5.5, qwen3.6,
mimo-v2.5, kimi-k2.6, minimax-m2.7) carry `(?!\d)` so a model with one
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

| Model ID                     | Input | Output | Regex pattern |
|------------------------------|-------|--------|---------------|
| `glm-4.7`                    |  0.38 |   1.74 | `glm-4\.7`    |
| `glm-5`                      |  0.60 |   2.08 | `glm-5`       |
| `glm-5.1`                    |  1.05 |   3.50 | `glm-5\.1`    |
| `z-ai/glm-5-turbo`           |  1.20 |   4.00 | `glm-5-turbo` |

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

### OpenAI (via OpenRouter)

| Model ID                     | Input  | Output  | Regex pattern        |
|------------------------------|--------|---------|----------------------|
| `openai/gpt-5.5-pro`         | 30.00  |  180.00 | `gpt-5\.5(?!\d).*pro\b` |
| `openai/gpt-5.5`             |  5.00  |   30.00 | `gpt-5\.5(?!\d)`     |

### DeepSeek V4

| Model ID                        | Input | Output | Regex pattern              |
|---------------------------------|-------|--------|----------------------------|
| `deepseek/deepseek-v4-pro`      |  1.74 |   3.48 | `deepseek[-_/.]v4[-_/.].*pro\b`   |
| `deepseek/deepseek-v4-flash`    |  0.14 |   0.28 | `deepseek[-_/.]v4[-_/.].*flash\b` |

### Xiaomi MiMo V2.5

| Model ID                     | Input | Output | Regex pattern        |
|------------------------------|-------|--------|----------------------|
| `xiaomi/mimo-v2.5-pro`       |  1.00 |   3.00 | `mimo[-_/.]v2\.5(?!\d).*pro\b` |
| `xiaomi/mimo-v2.5`           |  0.40 |   2.00 | `mimo[-_/.]v2\.5(?!\d)`        |

### Moonshot Kimi

| Model ID                     | Input  | Output | Regex pattern |
|------------------------------|--------|--------|---------------|
| `moonshotai/kimi-k2.6`       | 0.7448 |  4.655 | `kimi[-_/.]k2\.6(?!\d)` |

### MiniMax

| Model ID                     | Input | Output | Regex pattern      |
|------------------------------|-------|--------|--------------------|
| `minimax/minimax-m2.7`       |  0.30 |   1.20 | `minimax[-_/.]m2\.7(?!\d)` |

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
- **Fast mode** (research preview, **Opus 4.6 / 4.7 / 4.8 only**): a premium
  rate tier — Opus 4.6/4.7 bill at **6× standard** ($30 input / $150 output),
  Opus 4.8 at **2×** ($10 / $50). Prompt-caching multipliers apply *on top of*
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
