#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
session-metrics.py — Claude Code session cost estimator

Reads the JSONL conversation log and produces a timeline-ordered table of
per-turn token usage and estimated USD cost.

Usage:
  uv run python session-metrics.py                        # auto-detect from cwd
  uv run python session-metrics.py --session <uuid>       # specific session
  uv run python session-metrics.py --slug <slug>          # specific project slug
  uv run python session-metrics.py --list                 # list sessions for project
  uv run python session-metrics.py --project-cost         # all sessions, timeline + totals
  uv run python session-metrics.py --output json html     # export to exports/session-metrics/
  uv run python session-metrics.py --no-include-subagents # skip spawned agents (default: included)

--output accepts one or more of: text json csv md html
  Writes to <cwd>/exports/session-metrics/<name>_<timestamp>.<ext>
  Text is always printed to stdout; other formats are written to files.

Environment variables (all optional — CLI flags take precedence):
  CLAUDE_SESSION_ID       Session UUID to analyse
  CLAUDE_PROJECT_SLUG     Project slug override (e.g. -Volumes-foo-bar-project)
  CLAUDE_PROJECTS_DIR     Override ~/.claude/projects (default: ~/.claude/projects)
"""

import atexit  # noqa: I001 — block keeps `secrets`/`zoneinfo` re-imports below for sm.* test patching
import importlib.util as _ilu
import re
import secrets  # accessed as sm.secrets by tests; actual use is in _data.py  # noqa: F401
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # accessed as sm.ZoneInfo / sm.ZoneInfoNotFoundError by tests  # noqa: F401

# Bump when the parsed-entries shape changes — invalidates old parse caches.
# 1.1.0 (2026-04-30): cache format switched from gzip+JSON to pickle protocol 5.
# Bench measured -67% cold / -18% warm / -17% project on this single change
# (bench/results/README.md in the dev repo). Trade-off: cache files ~2× larger
# on disk (~9 MB → ~19 MB per typical session); acceptable for a developer-tool
# cache. Version bump invalidates every existing user blob exactly once.
_SCRIPT_VERSION = "1.1.0"
_SKILL_VERSION  = "1.80.1"  # embedded in every export; bump when plugin version bumps
# C.6: the date the built-in `_PRICING` table was last verified against the
# published rate card (mirrors the "Snapshot:" comment below). Embedded in
# every report so a reader can see how fresh the cost math is and decide
# whether to supply `--refresh-pricing` for any unresolved models.
_PRICING_SNAPSHOT_DATE = "2026-04-17"

# ---------------------------------------------------------------------------
# Pricing table  (USD per million tokens)
# See references/pricing.md for notes and source.
# ---------------------------------------------------------------------------
# Per-million-token rates (USD). Source: https://platform.claude.com/docs/en/about-claude/pricing
# Snapshot: 2026-04-17. Two cache-write tiers: `cache_write` = 5-minute TTL
# (1.25x base input), `cache_write_1h` = 1-hour TTL (2x base input). The
# per-entry split is read from `usage.cache_creation.ephemeral_{5m,1h}_input_tokens`
# when present; legacy transcripts without the nested object fall back to the
# 5-minute rate via `_cost`.
#
# IMPORTANT: Opus 4.5-and-later (4.5 / 4.6 / 4.7 / 4.8 / 4.9 / 5) use the NEW
# cheaper tier ($5/$25) introduced with the 4.5 generation. Opus 4 / 4.1 retain
# the OLD tier ($15/$75). Dict order matters for prefix fallback — more-specific
# entries must appear first.
_PRICING: dict[str, dict[str, float]] = {
    # --- Opus 4.5-generation (new tier: $5 input / $25 output) ---
    # `claude-opus-5` is a bare-major key (pre-provisioned, v1.44.0): assumed
    # same new tier, and as a prefix it catches every 5.x minor + `[1m]` + date
    # suffix in one entry. Review the rate if Anthropic re-tiers at Opus 5.0.
    "claude-opus-5":             {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    "claude-opus-4-9":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    "claude-opus-4-8":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    "claude-opus-4-7":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    "claude-opus-4-6":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    "claude-opus-4-5":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    # --- Opus 4 / 4.1 (old tier) — no plain string keys live here ---
    # NOTE: neither the bare "claude-opus-4" (removed v1.41.2) nor
    # "claude-opus-4-1" (removed v1.45.1) are plain keys in this dict. As prefix
    # keys they silently caught their two-digit extensions in the `_pricing_for`
    # prefix sweep and over-charged by 3x at OLD-tier $15/$75: "claude-opus-4"
    # caught any `claude-opus-4-N`, and "claude-opus-4-1" caught
    # `claude-opus-4-10`..`-19`. Both are now anchored regexes in
    # `_PRICING_PATTERNS` below, so only the exact IDs (+ their date / `[1m]`
    # forms) price OLD-tier; un-keyed future Opus 4 minors — two-digit
    # `4-10`+ included — route to the NEW $5/$25 tier via
    # `_PRICING_FAMILY_FALLBACKS` with an unknown-model warning. See the v1.41.2
    # and v1.45.1 changelog entries.
    # --- Sonnet 4.x + 3.7 (shared rates) ---
    # `claude-sonnet-5` bare-major key (pre-provisioned, v1.44.0): Sonnet has
    # held one rate tier across all minors, so a bare major catching every 5.x
    # variant is safe (same reasoning as the bare `claude-sonnet-4` below).
    "claude-sonnet-5":           {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4-9":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4-8":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4-7":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4-6":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4-5":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4":           {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-3-7-sonnet":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-3-5-sonnet":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    # --- Haiku 4.5 (own tier: $1 input / $5 output) ---
    # `claude-haiku-5` bare-major key (pre-provisioned, v1.44.0): assumed same
    # Haiku tier; as a prefix it catches every 5.x minor + `[1m]` + date suffix.
    "claude-haiku-5":            {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    "claude-haiku-4-9":          {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    "claude-haiku-4-8":          {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    "claude-haiku-4-7":          {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    "claude-haiku-4-6":          {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    "claude-haiku-4-5-20251001": {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    "claude-haiku-4-5":          {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    # --- Haiku 3.5 (older, cheaper input) ---
    "claude-3-5-haiku":          {"input":  0.80, "output":  4.00, "cache_read": 0.08,  "cache_write":  1.00, "cache_write_1h":  1.60},
    # --- Opus 3 (deprecated; old-tier rates) ---
    "claude-3-opus":             {"input": 15.00, "output": 75.00, "cache_read": 1.50,  "cache_write": 18.75, "cache_write_1h": 30.00},
    # --- Fable 5 (own premium tier: $10 input / $50 output) ---
    # New model family shipped 2026-06 (Claude Code CLI first; desktop later).
    # `claude-fable-5` is a bare-major key: as a prefix it catches every `5.x`
    # minor + `[1m]` + date suffix in one entry (same pattern as the bare-major
    # Opus/Sonnet/Haiku keys above). Cache columns follow the standard Anthropic
    # ratios off the $10 base input: read 0.1x = $1, 5m-write 1.25x = $12.50,
    # 1h-write 2x = $20. Review if Anthropic re-tiers at a future Fable major.
    "claude-fable-5":            {"input": 10.00, "output": 50.00, "cache_read": 1.00,  "cache_write": 12.50, "cache_write_1h": 20.00},
    # --- Non-Anthropic models (OpenRouter rates, 2026-04-25; no prompt caching) ---
    # GLM models — Z.ai / Zhipu AI
    "glm-4.7":                   {"input":  0.38, "output":  1.74, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    "glm-5":                     {"input":  0.60, "output":  2.08, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    "glm-5.1":                   {"input":  1.05, "output":  3.50, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # GLM-5.2 shares GLM-5.1's rate tier (Z.ai, 2026-06). Own key for export
    # traceability; a dedicated regex guard below keeps it off the cheaper bare
    # `glm-5` prefix (same trap documented for glm-5.1).
    "glm-5.2":                   {"input":  1.05, "output":  3.50, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # Google Gemma 4 — OpenRouter: google/gemma-4-26b-a4b-it @ $0.06/$0.33; prefix covers Ollama variants
    "google/gemma-4-26b-a4b":    {"input":  0.06, "output":  0.33, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    "gemma4":                    {"input":  0.06, "output":  0.33, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # Qwen3.5 9B — OpenRouter: qwen/qwen3.5-9b @ $0.10/$0.15
    "qwen3.5:9b":                {"input":  0.10, "output":  0.15, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # OpenAI GPT-5.5 family (via OpenRouter, 2026-04-25) — Pro before base
    "openai/gpt-5.5-pro":        {"input": 30.00, "output": 180.00, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    "openai/gpt-5.5":            {"input":  5.00, "output":  30.00, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # DeepSeek V4
    "deepseek/deepseek-v4-pro":  {"input":  1.74, "output":   3.48, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    "deepseek/deepseek-v4-flash":{"input":  0.14, "output":   0.28, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # Xiaomi MiMo V2.5 — Pro before base
    "xiaomi/mimo-v2.5-pro":      {"input":  1.00, "output":   3.00, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    "xiaomi/mimo-v2.5":          {"input":  0.40, "output":   2.00, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # Moonshot Kimi K2.6
    "moonshotai/kimi-k2.6":      {"input": 0.7448, "output":  4.655, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # Qwen 3.6 Plus
    "qwen/qwen3.6-plus":         {"input": 0.325,  "output":   1.95, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # MiniMax M2.7
    "minimax/minimax-m2.7":      {"input":  0.30, "output":   1.20, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    # GLM-5-Turbo (Z.ai) — must precede glm-5 in prefix scan; regex guard also added below
    "z-ai/glm-5-turbo":          {"input":  1.20, "output":   4.00, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
}
_DEFAULT_PRICING = {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75, "cache_write_1h": 6.00}
# Zero-rate tier for non-billable placeholder turns. Dynamic-workflow
# transcripts carry a single ``<synthetic>``-model orchestrator row per run
# (no real inference); pricing it at the Sonnet default would both overcharge
# and pollute the unknown-model advisory. Short-circuited in `_pricing_for`.
_ZERO_PRICING = {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0, "cache_write_1h": 0.0}
_SYNTHETIC_MODEL = "<synthetic>"

# Fast-mode (research preview) premium multipliers. Source: Anthropic pricing
# (https://platform.claude.com/docs/en/about-claude/pricing § "Fast mode
# pricing"). Fast mode is Opus-only and prices EVERY token category at a uniform
# premium over standard rates — prompt-caching multipliers apply on top of the
# fast base — so a single per-model factor applied to the computed token cost is
# exact (not an approximation). Keyed by model-id prefix; `[1m]` and date
# suffixes resolve via the prefix sweep in `_fast_multiplier_for`. Models absent
# here → 1.0 (no premium is ever invented for an unmapped model).
_FAST_MODE_MULTIPLIERS: dict[str, float] = {
    "claude-opus-4-8": 2.0,   # fast $10/$50  vs standard $5/$25
    "claude-opus-4-7": 6.0,   # fast $30/$150 vs standard $5/$25
    "claude-opus-4-6": 6.0,   # fast $30/$150 vs standard $5/$25
}
# Server-side web_search is billed per request, OUTSIDE the token rate
# ($10 / 1,000 searches = $0.01 per request). web_fetch has NO per-request
# charge (token-only), so it is intentionally not modelled. Source: Anthropic
# pricing § "Web search tool" / "Web fetch tool". This is a flat dollar charge,
# so it must be added AFTER any fast-mode multiplier (never scaled by it).
_WEB_SEARCH_REQUEST_USD = 0.01

# Regex patterns for flexible model-ID matching — checked between exact match and prefix
# sweep. re.search so partial IDs (no provider prefix, date suffixes, :tag qualifiers)
# still resolve. More-specific patterns must come first within each family.
#
# Boundary policy (v1.41.0):
#   * Numeric-suffix families (gpt-5.5, qwen3.6, mimo-v2.5, kimi-k2.6,
#     minimax-m2.7) carry ``(?!\d)`` so a model with one extra trailing digit
#     (e.g. ``gpt-5.55``, ``qwen3.60``) falls through to default Sonnet rates
#     instead of being mispriced as the shorter version.
#   * Provider/model separators use the class ``[-_/.]`` rather than a bare
#     ``.`` (which matched any character, including letters): keeps OpenRouter
#     dotted IDs (``deepseek.v4-flash``) compatible while blocking arbitrary
#     letter substitutions (``deepseekXv4Yflash``).
#   * Suffix tokens (``pro``, ``flash``, ``plus``) carry ``\b`` so
#     ``pro\b`` does not glue to other words.
#   * Within a family, the more-expensive variant (e.g. pro) is declared
#     first; this is a pricing-policy choice, not a regex bug — a hypothetical
#     ``deepseek-v4-flash-pro`` would price as pro by design.
_PRICING_PATTERNS: list[tuple[re.Pattern[str], dict[str, float]]] = [
    # OpenAI GPT-5.5 — Pro before base
    (re.compile(r"gpt-5\.5(?!\d).*pro\b",            re.I), _PRICING["openai/gpt-5.5-pro"]),
    (re.compile(r"gpt-5\.5(?!\d)",                   re.I), _PRICING["openai/gpt-5.5"]),
    # DeepSeek V4 (separator between provider prefix and v4 may vary)
    (re.compile(r"deepseek[-_/.]v4[-_/.].*pro\b",    re.I), _PRICING["deepseek/deepseek-v4-pro"]),
    (re.compile(r"deepseek[-_/.]v4[-_/.].*flash\b",  re.I), _PRICING["deepseek/deepseek-v4-flash"]),
    # Xiaomi MiMo V2.5 — Pro before base
    (re.compile(r"mimo[-_/.]v2\.5(?!\d).*pro\b",     re.I), _PRICING["xiaomi/mimo-v2.5-pro"]),
    (re.compile(r"mimo[-_/.]v2\.5(?!\d)",            re.I), _PRICING["xiaomi/mimo-v2.5"]),
    # Moonshot Kimi K2.6
    (re.compile(r"kimi[-_/.]k2\.6(?!\d)",            re.I), _PRICING["moonshotai/kimi-k2.6"]),
    # Qwen 3.6 Plus
    (re.compile(r"qwen3\.6(?!\d).*plus\b",           re.I), _PRICING["qwen/qwen3.6-plus"]),
    # MiniMax M2.7
    (re.compile(r"minimax[-_/.]m2\.7(?!\d)",         re.I), _PRICING["minimax/minimax-m2.7"]),
    # GLM-5-Turbo before the bare glm-5 prefix entry
    (re.compile(r"glm-5-turbo\b",                    re.I), _PRICING["z-ai/glm-5-turbo"]),
    # GLM-5.1 before the bare glm-5 prefix entry. `glm-5` is a strict prefix of
    # `glm-5.1`, so without this guard a suffixed variant (`glm-5.1-air`,
    # `glm-5.1:1m`, `glm-5.1-20260101`) prefix-matches the cheaper `glm-5` entry
    # and undercharges. `(?!\d)` keeps a hypothetical `glm-5.10`+ from gluing on.
    (re.compile(r"glm-5\.1(?!\d)",                   re.I), _PRICING["glm-5.1"]),
    # GLM-5.2 before the bare glm-5 prefix entry — identical guard rationale to
    # glm-5.1: `glm-5` is a strict prefix of `glm-5.2`, so without this a
    # suffixed variant (`glm-5.2-air`, `glm-5.2[1m]`, `glm-5.2-20260601`)
    # prefix-matches the cheaper `glm-5` entry and undercharges. `(?!\d)` keeps
    # a hypothetical `glm-5.20`+ from gluing on.
    (re.compile(r"glm-5\.2(?!\d)",                   re.I), _PRICING["glm-5.2"]),
    # ----- Opus 4.0 (anchored regex; replaces the prefix-fallback `claude-opus-4`
    # entry that was removed in v1.41.2). Without this anchored form, the bare
    # `claude-opus-4` prefix in `_PRICING` would silently catch any future
    # `claude-opus-4-N` (N >= 8 — see _PRICING_FAMILY_FALLBACKS below) and
    # over-charge by 3x at OLD-tier $15/$75. Match policy: the bare ID
    # `claude-opus-4` OR a single date-suffixed form `claude-opus-4-YYYYMMDD`
    # (8 digits). A `claude-opus-4-1` minor is handled by the anchored 4.1 regex
    # just below; `claude-opus-4-8` and other minors fall through to a
    # more-specific entry or the family fallback.
    (re.compile(r"^claude-opus-4(?:-\d{8})?$",       re.I),
        {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_write": 18.75, "cache_write_1h": 30.00}),
    # ----- Opus 4.1 (anchored regex; v1.45.1). Moved out of `_PRICING`, where
    # the plain `claude-opus-4-1` key prefix-matched the two-digit minors
    # `claude-opus-4-10`..`-19` and silently priced them at OLD $15/$75 (a 3x
    # overcharge once Anthropic ships a 4.10+). The `(?:-|\[|$)` boundary matches
    # `claude-opus-4-1` itself plus its date-suffix and `[1m]` forms, but NOT a
    # trailing digit — so `claude-opus-4-10`+ no longer matches here and instead
    # routes to the NEW-tier family fallback (with a warning).
    (re.compile(r"^claude-opus-4-1(?:-|\[|$)",       re.I),
        {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_write": 18.75, "cache_write_1h": 30.00}),
]

# Family-aware fallbacks (v1.41.2). Consulted by `_pricing_for` AFTER the exact
# match, the explicit `_PRICING_PATTERNS`, and the prefix sweep — only when
# the model truly has no specific entry. Each fallback hit also adds the
# model to `_UNKNOWN_MODELS_SEEN`, so the at-exit advisory tells the user
# to refresh `references/pricing.md`. The user gets a correct family-tier
# rate AND a nudge to add an explicit entry.
#
# Without these, two silent 3x overcharges leaked through:
#   * `claude-opus-4-8` (or any future Opus 4 minor >= 8) used to prefix-match
#     the bare `claude-opus-4` entry in `_PRICING` and price at OLD-tier
#     $15/$75 instead of NEW-tier $5/$25. The bare entry has been converted
#     to an anchored regex above so the prefix sweep no longer catches it.
#   * `claude-haiku-4-6` / `claude-haiku-5` have no Haiku prefix entry and
#     used to fall to `_DEFAULT_PRICING` (Sonnet $3/$15) instead of Haiku
#     $1/$5.
#
# Sonnet is intentionally omitted: `claude-sonnet-4` (a bare prefix entry
# in _PRICING) already correctly catches every `claude-sonnet-4-N` variant
# at Sonnet rates — Sonnet 4.x has held one rate tier across all minors,
# so the silent prefix-sweep behavior is correct for Sonnet.
#
# Boundary `(?:-|\[|$)` (v1.44.0): the trailing alternation accepts a `-`
# (date suffix), the literal `[` of a `[1m]` context tag, or end-of-string.
# The `\[` was added so an un-keyed future `[1m]` variant (e.g. a hypothetical
# `claude-opus-6[1m]`) still resolves to the family tier instead of falling to
# `_DEFAULT_PRICING` (Sonnet $3) — the same `[1m]` evasion that mispriced
# `claude-opus-4-8[1m]` before its explicit key landed in v1.43.0.
# Two-digit minors (v1.45.1): `claude-opus-4-10`..`-19` are caught by the Opus-4
# minor fallback's `\d{2,}` alternation → NEW $5/$25 tier WITH a warning. (An
# earlier comment here claimed `claude-opus-4-99` "falls through and warns" —
# that was wrong: `4-90`..`-99` prefix-match the explicit `claude-opus-4-9` key
# at step 3 and resolve to $5 SILENTLY — correct tier, no warning, acceptable.)
_PRICING_FAMILY_FALLBACKS: list[tuple[re.Pattern[str], dict[str, float]]] = [
    # Opus 4 minors 5-9 are ALL explicit keys (v1.44.0), caught by exact match /
    # prefix sweep before this fires. The `\d{2,}` alternation (v1.45.1) ALSO
    # catches un-keyed TWO-digit minors (e.g. `claude-opus-4-10`..`-19`): they no
    # longer prefix-match the old `claude-opus-4-1` key (now an anchored regex),
    # so they land here and get the conservative NEW $5/$25 tier + a warning
    # rather than silently defaulting to Sonnet $3.
    (re.compile(r"^claude-opus-4-(?:[5-9]|\d{2,})(?:-|\[|$)", re.I), _PRICING["claude-opus-4-7"]),
    # Future Opus majors (6+). `claude-opus-5` is an explicit bare-major key
    # (catches all 5.x), so this back-stops 6+. New tier is the conservative
    # bet — under-counting by ~10% if Anthropic raises prices beats the prior
    # 3x silent overcharge from the OLD-tier prefix.
    (re.compile(r"^claude-opus-(?:[5-9]|\d{2,})(?:-|\[|$)", re.I), _PRICING["claude-opus-4-7"]),
    # Haiku 4 minors 6-9 are now ALL explicit keys (v1.44.0); like the Opus 4
    # minor regex above, this is now a fully-shadowed defensive back-stop.
    (re.compile(r"^claude-haiku-4-[6-9](?:-|\[|$)",         re.I), _PRICING["claude-haiku-4-5"]),
    # Future Haiku majors (6+). `claude-haiku-5` is an explicit bare-major key,
    # so this back-stops 6+. Same conservative-bet reasoning as Opus.
    (re.compile(r"^claude-haiku-(?:[5-9]|\d{2,})(?:-|\[|$)", re.I), _PRICING["claude-haiku-4-5"]),
    # Future Fable majors (6+). `claude-fable-5` is an explicit bare-major key
    # (catches all 5.x), so this back-stops 6+. Fable is a non-default premium
    # family, so — like Opus/Haiku and unlike Sonnet — it needs an explicit
    # fallback; without it a future `claude-fable-6` would default to Sonnet $3
    # (a ~70% under-count on a $10 model). Holds the Fable 5 tier as the bet.
    (re.compile(r"^claude-fable-(?:[6-9]|\d{2,})(?:-|\[|$)", re.I), _PRICING["claude-fable-5"]),
]

# Module-level advisory state — populated during parsing, printed via atexit.
# Sets/lists avoid the `global` keyword; atexit fires at normal process exit.
_UNKNOWN_MODELS_SEEN: set[str] = set()
_FAST_MODE_TURNS: list[int] = [0]  # [0] is the running count


def _print_run_advisories() -> None:
    if _UNKNOWN_MODELS_SEEN:
        names = ", ".join(sorted(_UNKNOWN_MODELS_SEEN))
        # v1.41.2: family-fallback hits route to the family's most recent
        # tier (NEW Opus / Haiku / Sonnet) rather than always landing on
        # _DEFAULT_PRICING. The phrasing "fallback rates" covers both
        # paths; users who want the exact rate should check the table.
        print(
            f"[warn] Unknown model(s) priced at fallback rates "
            f"(verify in references/pricing.md): {names}.",
            file=sys.stderr,
        )
    if _FAST_MODE_TURNS[0]:
        n = _FAST_MODE_TURNS[0]
        plural = "s" if n != 1 else ""
        if _FAST_PREMIUM_DISABLED:
            print(
                f"[note] {n} fast-mode turn{plural} detected; the fast-mode "
                "premium (Opus 4.6/4.7 6×, 4.8 2× standard rates) was SUPPRESSED "
                "via --no-fast-premium, so cost is under-stated for those turns. "
                "See references/pricing.md § Fast mode.",
                file=sys.stderr,
            )
        else:
            print(
                f"[note] {n} fast-mode turn{plural} detected; priced at the "
                "fast-mode premium (Opus 4.6/4.7 6×, 4.8 2× standard rates). "
                "Pass --no-fast-premium to reproduce pre-premium numbers. "
                "See references/pricing.md § Fast mode.",
                file=sys.stderr,
            )


atexit.register(_print_run_advisories)

# Register this module under the canonical "session_metrics" key so that
# leaf modules' _sm() helper resolves correctly whether the script is run
# directly (__name__ == "__main__") or loaded via spec_from_file_location.
sys.modules.setdefault("session_metrics", sys.modules[__name__])


# ---------------------------------------------------------------------------
# Leaf module loader — siblings in the same scripts/ directory.
# Uses spec_from_file_location (matching _load_compare_module pattern) so
# sys.path is never mutated globally. Each module is registered in sys.modules
# so cross-sibling imports (e.g. _user_prompt importing from _dt) resolve.
# Modules are loaded in dependency order: _dt before _user_prompt.
# ---------------------------------------------------------------------------

def _load_leaf(name: str):
    if name in sys.modules:
        return sys.modules[name]
    _here = Path(__file__).resolve().parent
    spec = _ilu.spec_from_file_location(name, _here / f"{name}.py")
    if spec is None or spec.loader is None:
        print(f"[error] Cannot locate leaf module {name!r} next to "
              f"session-metrics.py", file=sys.stderr)
        sys.exit(1)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load _constants first — leaves that need def-time literals
# (``def fn(x: int = _NAME)``) import from it at their own load time.
_co_m = _load_leaf("_constants")
_CACHE_BREAK_DEFAULT_THRESHOLD = _co_m._CACHE_BREAK_DEFAULT_THRESHOLD
_MODEL_CONTEXT_WINDOWS         = _co_m._MODEL_CONTEXT_WINDOWS
_DEFAULT_CONTEXT_WINDOW        = _co_m._DEFAULT_CONTEXT_WINDOW
_LONG_CONTEXT_WINDOW           = _co_m._LONG_CONTEXT_WINDOW
del _co_m

_dt_m = _load_leaf("_dt")
_parse_iso_dt = _dt_m._parse_iso_dt
del _dt_m

_tz_m = _load_leaf("_tz")
_local_tz_offset  = _tz_m._local_tz_offset
_local_tz_label   = _tz_m._local_tz_label
_parse_peak_hours = _tz_m._parse_peak_hours
_build_peak       = _tz_m._build_peak
_resolve_tz       = _tz_m._resolve_tz
del _tz_m

_up_m = _load_leaf("_user_prompt")
_is_user_prompt          = _up_m._is_user_prompt
_extract_user_timestamps = _up_m._extract_user_timestamps
del _up_m

_je_m = _load_leaf("_json_export")
_tod_for_json            = _je_m._tod_for_json
_REDACTED_TURN_FIELDS    = _je_m._REDACTED_TURN_FIELDS
_REDACTED_PLACEHOLDER    = _je_m._REDACTED_PLACEHOLDER
_redact_turns_for_json   = _je_m._redact_turns_for_json
render_json              = _je_m.render_json
_render_instance_json    = _je_m._render_instance_json
del _je_m

_tod_m = _load_leaf("_time_of_day")
_TOD_PERIODS               = _tod_m._TOD_PERIODS
_bucket_time_of_day        = _tod_m._bucket_time_of_day
_build_hour_of_day         = _tod_m._build_hour_of_day
_build_weekday_hour_matrix = _tod_m._build_weekday_hour_matrix
_build_time_of_day         = _tod_m._build_time_of_day
_is_off_peak_local         = _tod_m._is_off_peak_local
del _tod_m

_an_m = _load_leaf("_analytics")
_INSIGHT_PARALLEL_PCT_THRESHOLD       = _an_m._INSIGHT_PARALLEL_PCT_THRESHOLD
_INSIGHT_LONG_SESSION_HOURS           = _an_m._INSIGHT_LONG_SESSION_HOURS
_INSIGHT_LONG_SESSION_PCT_THRESHOLD   = _an_m._INSIGHT_LONG_SESSION_PCT_THRESHOLD
_INSIGHT_BIG_CONTEXT_TOKENS           = _an_m._INSIGHT_BIG_CONTEXT_TOKENS
_INSIGHT_BIG_CONTEXT_PCT_THRESHOLD    = _an_m._INSIGHT_BIG_CONTEXT_PCT_THRESHOLD
_INSIGHT_BIG_CACHE_MISS_TOKENS        = _an_m._INSIGHT_BIG_CACHE_MISS_TOKENS
_INSIGHT_BIG_CACHE_MISS_PCT_THRESHOLD = _an_m._INSIGHT_BIG_CACHE_MISS_PCT_THRESHOLD
_INSIGHT_SUBAGENT_TASK_COUNT          = _an_m._INSIGHT_SUBAGENT_TASK_COUNT
_INSIGHT_SUBAGENT_PCT_THRESHOLD       = _an_m._INSIGHT_SUBAGENT_PCT_THRESHOLD
_INSIGHT_TOOL_DOMINANCE_MIN_CALLS     = _an_m._INSIGHT_TOOL_DOMINANCE_MIN_CALLS
_INSIGHT_OFF_PEAK_PCT_THRESHOLD       = _an_m._INSIGHT_OFF_PEAK_PCT_THRESHOLD
_INSIGHT_COST_CONCENTRATION_TOP_N     = _an_m._INSIGHT_COST_CONCENTRATION_TOP_N
_INSIGHT_COST_CONCENTRATION_PCT       = _an_m._INSIGHT_COST_CONCENTRATION_PCT
_INSIGHT_COST_CONCENTRATION_MIN_TURNS = _an_m._INSIGHT_COST_CONCENTRATION_MIN_TURNS
_session_task_count                   = _an_m._session_task_count
_turn_total_input                     = _an_m._turn_total_input
_model_family                         = _an_m._model_family
_percentile                           = _an_m._percentile
_fmt_long_duration                    = _an_m._fmt_long_duration
_compare_state_marker_path            = _an_m._compare_state_marker_path
_touch_compare_state_marker           = _an_m._touch_compare_state_marker
_has_compare_state_marker             = _an_m._has_compare_state_marker
_scan_project_family_mix              = _an_m._scan_project_family_mix
_version_suffix_of_family             = _an_m._version_suffix_of_family
_order_family_pair                    = _an_m._order_family_pair
_compute_model_compare_insight        = _an_m._compute_model_compare_insight
_compute_usage_insights               = _an_m._compute_usage_insights
del _an_m

_ch_m = _load_leaf("_charts")
_build_cache_trend_sparkline_svg = _ch_m._build_cache_trend_sparkline_svg
_CHART_PAGE                   = _ch_m._CHART_PAGE
_VENDOR_CHARTS_DIR            = Path(_ch_m.__file__ or __file__).resolve().parent / "vendor" / "charts"
_ALLOW_UNVERIFIED_CHARTS      = False
# --no-fast-premium: when True, suppress the fast-mode cost multiplier so a
# report reproduces pre-fast-premium numbers (parity with exports generated
# before fast-mode pricing was applied). Set from the CLI; read in `_cost`,
# `_no_cache_cost`, and the `extra_1h_cost` derivation.
_FAST_PREMIUM_DISABLED        = False
_PROJECTS_DIR_OVERRIDE: Path | None = None
# v1.41.0: parse-cache and export directories are operator-overridable so
# users with multiple Claude Code installs (CI, ephemeral envs, shared boxes)
# can redirect each independently. Resolution order: --flag > env var > default.
_CACHE_DIR_OVERRIDE:    Path | None = None
_EXPORT_DIR_OVERRIDE:   Path | None = None
VendorChartVerificationError  = _ch_m.VendorChartVerificationError
_chart_verification_failure   = _ch_m._chart_verification_failure
_load_chart_manifest          = _ch_m._load_chart_manifest
_read_vendor_files            = _ch_m._read_vendor_files
_read_vendor_js               = _ch_m._read_vendor_js
_read_vendor_css              = _ch_m._read_vendor_css
_hc_scripts                   = _ch_m._hc_scripts
_extract_chart_series         = _ch_m._extract_chart_series
_render_chart_highcharts      = _ch_m._render_chart_highcharts
_build_lib_chart_pages        = _ch_m._build_lib_chart_pages
_render_chart_uplot           = _ch_m._render_chart_uplot
_render_chart_chartjs         = _ch_m._render_chart_chartjs
_render_chart_none            = _ch_m._render_chart_none
CHART_RENDERERS               = _ch_m.CHART_RENDERERS
_build_chart_html             = _ch_m._build_chart_html
_svg_scale                    = _ch_m._svg_scale
_build_cache_efficiency_svg   = _ch_m._build_cache_efficiency_svg
del _ch_m

_tp_m = _load_leaf("_turn_parser")
_EXIT_CMD_MARKER              = _tp_m._EXIT_CMD_MARKER
_CONTINUE_FROM_RESUME_MARKER  = _tp_m._CONTINUE_FROM_RESUME_MARKER
_RESUME_LOOKBACK_USER_ENTRIES = _tp_m._RESUME_LOOKBACK_USER_ENTRIES
_resume_fingerprint_match     = _tp_m._resume_fingerprint_match
_extract_turns                = _tp_m._extract_turns
_extract_compaction_events    = _tp_m._extract_compaction_events
_SLASH_WRAPPED_RE             = _tp_m._SLASH_WRAPPED_RE
_SLASH_BARE_RE                = _tp_m._SLASH_BARE_RE
_XML_MARKER_RE                = _tp_m._XML_MARKER_RE
_ASSISTANT_TEXT_CAP           = _tp_m._ASSISTANT_TEXT_CAP
_PROMPT_TEXT_CAP              = _tp_m._PROMPT_TEXT_CAP
_TOOL_RESULT_TEXT_CAP         = _tp_m._TOOL_RESULT_TEXT_CAP
_extract_tool_results         = _tp_m._extract_tool_results
_tool_input_hash             = _tp_m._tool_input_hash
_tool_input_file_path         = _tp_m._tool_input_file_path
_flatten_tool_result_content  = _tp_m._flatten_tool_result_content
_cache_write_split            = _tp_m._cache_write_split
_cost                         = _tp_m._cost
_advisor_info                 = _tp_m._advisor_info
_no_cache_cost                = _tp_m._no_cache_cost
_count_content_blocks         = _tp_m._count_content_blocks
_truncate                     = _tp_m._truncate
_extract_user_prompt_text     = _tp_m._extract_user_prompt_text
_extract_slash_command        = _tp_m._extract_slash_command
_extract_assistant_text       = _tp_m._extract_assistant_text
_summarise_tool_input         = _tp_m._summarise_tool_input
_build_turn_record            = _tp_m._build_turn_record
_fmt_ts                       = _tp_m._fmt_ts
del _tp_m

_mr_m = _load_leaf("_md_render")
COL                             = _mr_m.COL
_COL_MODE_SUFFIX                = _mr_m._COL_MODE_SUFFIX
_COL_CONTENT_SUFFIX             = _mr_m._COL_CONTENT_SUFFIX
COL_M                           = _mr_m.COL_M
_text_format                    = _mr_m._text_format
_text_table_headers             = _mr_m._text_table_headers
_report_has_any                 = _mr_m._report_has_any
_has_fast                       = _mr_m._has_fast
_has_1h_cache                   = _mr_m._has_1h_cache
_has_thinking                   = _mr_m._has_thinking
_has_tool_use                   = _mr_m._has_tool_use
_has_content_blocks             = _mr_m._has_content_blocks
_fmt_generated_at               = _mr_m._fmt_generated_at
_short_tz_label                 = _mr_m._short_tz_label
_fmt_epoch_local                = _mr_m._fmt_epoch_local
_fmt_cwr_row                    = _mr_m._fmt_cwr_row
_fmt_cwr_subtotal               = _mr_m._fmt_cwr_subtotal
_row_text                       = _mr_m._row_text
_subtotal_text                  = _mr_m._subtotal_text
_text_legend                    = _mr_m._text_legend
render_text                     = _mr_m.render_text
render_csv                      = _mr_m.render_csv
render_md                       = _mr_m.render_md
_fmt_duration                   = _mr_m._fmt_duration
_build_subagent_share_md        = _mr_m._build_subagent_share_md
_build_within_session_split_md  = _mr_m._build_within_session_split_md
_build_workflow_companion_md    = _mr_m._build_workflow_companion_md
_build_tasks_companion_md       = _mr_m._build_tasks_companion_md
_build_insights_companion_md    = _mr_m._build_insights_companion_md
_md_italic_safe                 = _mr_m._md_italic_safe
_build_usage_insights_md        = _mr_m._build_usage_insights_md
_build_waste_analysis_md        = _mr_m._build_waste_analysis_md
_build_cache_efficiency_md      = _mr_m._build_cache_efficiency_md
_build_velocity_md              = _mr_m._build_velocity_md
_build_session_shape_histograms_md = _mr_m._build_session_shape_histograms_md
_build_cache_economics_md       = _mr_m._build_cache_economics_md
_build_project_concentration_md = _mr_m._build_project_concentration_md
_build_activity_heatmap_md      = _mr_m._build_activity_heatmap_md
_build_session_activity_by_hour_md = _mr_m._build_session_activity_by_hour_md
_build_cost_over_time_md        = _mr_m._build_cost_over_time_md
del _mr_m

_cl_m = _load_leaf("_cli")
_SESSION_RE                     = _cl_m._SESSION_RE
_SLUG_RE                        = _cl_m._SLUG_RE
_validate_session_id            = _cl_m._validate_session_id
_validate_slug                  = _cl_m._validate_slug
_projects_dir                   = _cl_m._projects_dir
_ensure_within_projects         = _cl_m._ensure_within_projects
_cwd_to_slug                    = _cl_m._cwd_to_slug
_find_jsonl_files               = _cl_m._find_jsonl_files
_list_all_projects              = _cl_m._list_all_projects
_slug_to_friendly_path          = _cl_m._slug_to_friendly_path
_resolve_session                = _cl_m._resolve_session
_env_validated                  = _cl_m._env_validated
_env_slug                       = _cl_m._env_slug
_env_session_id                 = _cl_m._env_session_id
_list_sessions                  = _cl_m._list_sessions
_build_parser                   = _cl_m._build_parser
_maybe_warn_chart_license       = _cl_m._maybe_warn_chart_license
_load_compare_module            = _cl_m._load_compare_module
main                            = _cl_m.main
del _cl_m

_di_m = _load_leaf("_dispatch")
_export_dir                     = _di_m._export_dir
_write_output                   = _di_m._write_output
_unique_run_ts                  = _di_m._unique_run_ts
_ts_sort_key                    = _di_m._ts_sort_key
_scan_export_runs               = _di_m._scan_export_runs
_write_export_manifest          = _di_m._write_export_manifest
_run_prune_exports              = _di_m._run_prune_exports
_SUBAGENT_FILENAME_RE           = _di_m._SUBAGENT_FILENAME_RE
_resolve_subagent_type          = _di_m._resolve_subagent_type
_load_session                   = _di_m._load_session
_slim_blocks_turn               = _di_m._slim_blocks_turn
_run_single_session             = _di_m._run_single_session
_run_render_tasks               = _di_m._run_render_tasks
_run_prepare_tasks              = _di_m._run_prepare_tasks
_run_prepare_insights           = _di_m._run_prepare_insights
_run_render_insights            = _di_m._run_render_insights
_run_project_cost               = _di_m._run_project_cost
_run_all_projects               = _di_m._run_all_projects
_instance_export_root           = _di_m._instance_export_root
_dispatch_instance              = _di_m._dispatch_instance
_render_instance_text           = _di_m._render_instance_text
_render_instance_csv            = _di_m._render_instance_csv
_render_instance_md             = _di_m._render_instance_md
_render_instance_html           = _di_m._render_instance_html
_print_self_cost_summary        = _di_m._print_self_cost_summary
_dispatch                       = _di_m._dispatch
del _di_m

_hs_m = _load_leaf("_html_sections")
_fmt_content_cell               = _hs_m._fmt_content_cell
_fmt_content_title              = _hs_m._fmt_content_title
_footer_text                    = _hs_m._footer_text
_session_duration_stats         = _hs_m._session_duration_stats
_build_session_duration_html    = _hs_m._build_session_duration_html
_fmt_delta_pct                  = _hs_m._fmt_delta_pct
_build_weekly_rollup_html       = _hs_m._build_weekly_rollup_html
_build_session_blocks_html      = _hs_m._build_session_blocks_html
_build_tod_epoch_blob           = _hs_m._build_tod_epoch_blob
_build_hour_of_day_html         = _hs_m._build_hour_of_day_html
_build_punchcard_html           = _hs_m._build_punchcard_html
_tz_dropdown_options            = _hs_m._tz_dropdown_options
_build_tod_heatmap_html         = _hs_m._build_tod_heatmap_html
_fmt_cost                       = _hs_m._fmt_cost
_build_by_skill_html            = _hs_m._build_by_skill_html
_build_request_units_html       = _hs_m._build_request_units_html
_build_by_subagent_type_html    = _hs_m._build_by_subagent_type_html
_build_by_workflow_html         = _hs_m._build_by_workflow_html
_build_workflow_companion_html  = _hs_m._build_workflow_companion_html
_build_tasks_companion_html     = _hs_m._build_tasks_companion_html
_build_insights_companion_html  = _hs_m._build_insights_companion_html
_md_inline_to_html              = _hs_m._md_inline_to_html
_build_tasks_placeholder_html   = _hs_m._build_tasks_placeholder_html
_build_export_manifest_html     = _hs_m._build_export_manifest_html
_build_subagent_share_card_html = _hs_m._build_subagent_share_card_html
_build_subagent_turn_share_card_html = _hs_m._build_subagent_turn_share_card_html
_build_plan_leverage_card_html  = _hs_m._build_plan_leverage_card_html
_build_ttl_mix_card_html        = _hs_m._build_ttl_mix_card_html
_build_thinking_card_html       = _hs_m._build_thinking_card_html
_build_tool_calls_card_html     = _hs_m._build_tool_calls_card_html
_build_advisor_card_html        = _hs_m._build_advisor_card_html
_build_partial_hit_card_html    = _hs_m._build_partial_hit_card_html
_build_window_ribbon_html       = _hs_m._build_window_ribbon_html
_build_attribution_coverage_html = _hs_m._build_attribution_coverage_html
_build_within_session_split_html = _hs_m._build_within_session_split_html
_build_cache_breaks_html        = _hs_m._build_cache_breaks_html
_build_usage_insights_html      = _hs_m._build_usage_insights_html
_build_waste_analysis_html      = _hs_m._build_waste_analysis_html
_theme_css                      = _hs_m._theme_css
_theme_picker_markup            = _hs_m._theme_picker_markup
_theme_bootstrap_head_js        = _hs_m._theme_bootstrap_head_js
_theme_bootstrap_body_js        = _hs_m._theme_bootstrap_body_js
_overlay_css                    = _hs_m._overlay_css
_overlay_js                     = _hs_m._overlay_js
_stamp_sections_and_build_chips = _hs_m._stamp_sections_and_build_chips
_OVERLAY_NAMED_SECTIONS         = _hs_m._OVERLAY_NAMED_SECTIONS
_build_chartrail_section_html   = _hs_m._build_chartrail_section_html
_chartrail_script               = _hs_m._chartrail_script
_build_daily_cost_rail_html     = _hs_m._build_daily_cost_rail_html
_daily_cost_rail_script         = _hs_m._daily_cost_rail_script
_build_cache_efficiency_html    = _hs_m._build_cache_efficiency_html
_build_velocity_html            = _hs_m._build_velocity_html
_build_cost_over_time_svg_html  = _hs_m._build_cost_over_time_svg_html
_squarify                       = _hs_m._squarify
_build_cost_treemap_html        = _hs_m._build_cost_treemap_html
_build_vital_signs_html         = _hs_m._build_vital_signs_html
_build_session_shape_histograms_html = _hs_m._build_session_shape_histograms_html
_build_cache_economics_html     = _hs_m._build_cache_economics_html
_build_project_concentration_html = _hs_m._build_project_concentration_html
_build_activity_heatmap_html    = _hs_m._build_activity_heatmap_html
_build_session_activity_by_hour_html = _hs_m._build_session_activity_by_hour_html
render_html                     = _hs_m.render_html
del _hs_m

_rp_m = _load_leaf("_report")
_compute_subagent_share             = _rp_m._compute_subagent_share
_build_compaction_summary           = _rp_m._build_compaction_summary
_compute_within_session_split       = _rp_m._compute_within_session_split
_compute_window_stats               = _rp_m._compute_window_stats
_compute_cache_economics            = _rp_m._compute_cache_economics
_compute_project_concentration      = _rp_m._compute_project_concentration
_compute_activity_heatmap           = _rp_m._compute_activity_heatmap
_compute_instance_subagent_share    = _rp_m._compute_instance_subagent_share
_median                             = _rp_m._median
_compute_prompt_anchor_indices      = _rp_m._compute_prompt_anchor_indices
_attribute_subagent_tokens          = _rp_m._attribute_subagent_tokens
_build_report                       = _rp_m._build_report
_build_resumes                      = _rp_m._build_resumes
_project_summary_from_report        = _rp_m._project_summary_from_report
_build_instance_daily               = _rp_m._build_instance_daily
_aggregate_totals                   = _rp_m._aggregate_totals
_aggregate_models                   = _rp_m._aggregate_models
_merge_bucket_rows                  = _rp_m._merge_bucket_rows
_aggregate_attribution_summary      = _rp_m._aggregate_attribution_summary
_build_instance_report              = _rp_m._build_instance_report
del _rp_m

_da_m = _load_leaf("_data")
_pricing_for                = _da_m._pricing_for
_load_pricing_supplement    = _da_m._load_pricing_supplement
_fast_multiplier_for        = _da_m._fast_multiplier_for
_parse_jsonl                = _da_m._parse_jsonl
_parse_cache_dir            = _da_m._parse_cache_dir
_parse_cache_key            = _da_m._parse_cache_key
_cached_parse_jsonl         = _da_m._cached_parse_jsonl
_prune_cache_global         = _da_m._prune_cache_global
_CONTENT_LETTERS            = _da_m._CONTENT_LETTERS
_BLOCK_WINDOW_SEC           = _da_m._BLOCK_WINDOW_SEC
_parse_iso_epoch            = _da_m._parse_iso_epoch
_build_session_blocks       = _da_m._build_session_blocks
_build_weekly_rollup        = _da_m._build_weekly_rollup
_weekly_block_counts        = _da_m._weekly_block_counts
_derive_total_fields        = _da_m._derive_total_fields
_totals_from_turns          = _da_m._totals_from_turns
_add_totals                 = _da_m._add_totals
_model_breakdown            = _da_m._model_breakdown
_detect_cache_breaks        = _da_m._detect_cache_breaks
_TURN_CHARACTER_LABELS      = _da_m._TURN_CHARACTER_LABELS
_RISK_CATEGORIES            = _da_m._RISK_CATEGORIES
_PASTE_BOMB_CHARS           = _da_m._PASTE_BOMB_CHARS
_EXT_GROUP                  = _da_m._EXT_GROUP
_BASH_PATH_RE               = _da_m._BASH_PATH_RE
_READ_EXT_RE                = _da_m._READ_EXT_RE
_analyze_stop_reasons       = _da_m._analyze_stop_reasons
_detect_retry_chains        = _da_m._detect_retry_chains
_assign_context_segments    = _da_m._assign_context_segments
_detect_file_reaccesses     = _da_m._detect_file_reaccesses
_detect_verbose_edits       = _da_m._detect_verbose_edits
_classify_turn              = _da_m._classify_turn
_build_waste_analysis       = _da_m._build_waste_analysis
_empty_skill_row            = _da_m._empty_skill_row
_accumulate_bucket          = _da_m._accumulate_bucket
_finalise_skill_rows        = _da_m._finalise_skill_rows
_build_by_skill             = _da_m._build_by_skill
_build_request_units        = _da_m._build_request_units
_compute_velocity_stats     = _da_m._compute_velocity_stats
_VELOCITY_CYCLE_CAP_S       = _da_m._VELOCITY_CYCLE_CAP_S
_compute_session_shape_histograms = _da_m._compute_session_shape_histograms
_compute_session_activity_by_hour = _da_m._compute_session_activity_by_hour
_HIST_DURATION_LABELS       = _da_m._HIST_DURATION_LABELS
_HIST_TURN_LABELS           = _da_m._HIST_TURN_LABELS
_HIST_COST_LABELS           = _da_m._HIST_COST_LABELS
_detect_multi_intent        = _da_m._detect_multi_intent
_assemble_tasks             = _da_m._assemble_tasks
_build_tasks_skeleton       = _da_m._build_tasks_skeleton
_render_tasks_worksheet     = _da_m._render_tasks_worksheet
_assemble_insights          = _da_m._assemble_insights
_build_insights_skeleton    = _da_m._build_insights_skeleton
_build_insights_digest      = _da_m._build_insights_digest
_insights_facts             = _da_m._insights_facts
_insights_corpus_units      = _da_m._insights_corpus_units
_INSIGHTS_SCHEMA_VERSION    = _da_m._INSIGHTS_SCHEMA_VERSION
_INSIGHTS_LENSES            = _da_m._INSIGHTS_LENSES
_INSIGHTS_DIGEST_UNIT_CAP   = _da_m._INSIGHTS_DIGEST_UNIT_CAP
_INSIGHTS_SNIPPET_CAP       = _da_m._INSIGHTS_SNIPPET_CAP
_INSIGHTS_SECTION_STUBS     = _da_m._INSIGHTS_SECTION_STUBS
_cluster_request_units      = _da_m._cluster_request_units
_suggest_verdict            = _da_m._suggest_verdict
_seed_title                 = _da_m._seed_title
_TASKS_GROUPING_SCHEMA_VERSION = _da_m._TASKS_GROUPING_SCHEMA_VERSION
_SELF_COST_SKILL_NAMES      = _da_m._SELF_COST_SKILL_NAMES
_summarize_self_cost        = _da_m._summarize_self_cost
_empty_subagent_row         = _da_m._empty_subagent_row
_finalise_subagent_rows     = _da_m._finalise_subagent_rows
_build_by_subagent_type     = _da_m._build_by_subagent_type
_build_by_workflow          = _da_m._build_by_workflow
_write_evidence_pack        = _da_m._write_evidence_pack
_csv_safe                   = _da_m._csv_safe
_SafeCsvWriter              = _da_m._SafeCsvWriter
del _da_m

_he_m = _load_leaf("_health")
_build_session_health           = _he_m.build_session_health
_build_session_behavior         = _he_m.build_session_behavior
_classify_outcome               = _he_m.classify_outcome
_compute_tool_health            = _he_m.compute_tool_health
_compute_context_pressure       = _he_m.compute_context_pressure
_compute_health_score           = _he_m.compute_health_score
_detect_automated_session       = _he_m.detect_automated_session
_health_context_window_for      = _he_m._context_window_for
del _he_m

_inv_m = _load_leaf("_invariants")
_run_invariants                 = _inv_m._run_invariants
_format_invariant_results       = _inv_m._format_invariant_results
_invariants_exit_code           = _inv_m._invariants_exit_code
_INVARIANT_EXIT_CODE            = _inv_m._INVARIANT_EXIT_CODE
del _inv_m


# ---------------------------------------------------------------------------
# Output dispatch
# ---------------------------------------------------------------------------

_RENDERERS = {
    "text": render_text,
    "json": render_json,
    "csv":  render_csv,
    "md":   render_md,
    "html": render_html,
}
if __name__ == "__main__":
    main()
