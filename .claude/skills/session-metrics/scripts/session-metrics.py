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
_SKILL_VERSION  = "1.43.0"  # embedded in every export; bump when plugin version bumps

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
# IMPORTANT: Opus 4.5 / 4.6 / 4.7 use the NEW cheaper tier ($5/$25) introduced
# with the 4.5 generation. Opus 4 / 4.1 retain the OLD tier ($15/$75). Dict
# order matters for prefix fallback — more-specific entries must appear first.
_PRICING: dict[str, dict[str, float]] = {
    # --- Opus 4.5-generation (new tier: $5 input / $25 output) ---
    "claude-opus-4-8":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    "claude-opus-4-7":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    "claude-opus-4-6":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    "claude-opus-4-5":           {"input":  5.00, "output": 25.00, "cache_read": 0.50,  "cache_write":  6.25, "cache_write_1h": 10.00},
    # --- Opus 4 / 4.1 (old tier, retained for historical sessions) ---
    "claude-opus-4-1":           {"input": 15.00, "output": 75.00, "cache_read": 1.50,  "cache_write": 18.75, "cache_write_1h": 30.00},
    # NOTE (v1.41.2): the bare "claude-opus-4" key is intentionally NOT in
    # this dict. It used to live here, but the prefix-sweep in `_pricing_for`
    # would silently catch any future `claude-opus-4-N` (e.g. `claude-opus-4-9`)
    # and over-charge by 3x at OLD-tier rates. The Opus 4.0 ID and its
    # date-suffixed forms are now matched by an anchored regex in
    # `_PRICING_PATTERNS` below; future Opus 4 minors without an explicit key
    # (4-9+) are routed to the NEW $5/$25 tier via `_PRICING_FAMILY_FALLBACKS`
    # with an unknown-model warning. See the bug analysis in the v1.41.2
    # changelog entry.
    # --- Sonnet 4.x + 3.7 (shared rates) ---
    "claude-sonnet-4-7":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4-6":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4-5":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-sonnet-4":           {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-3-7-sonnet":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    "claude-3-5-sonnet":         {"input":  3.00, "output": 15.00, "cache_read": 0.30,  "cache_write":  3.75, "cache_write_1h":  6.00},
    # --- Haiku 4.5 (own tier: $1 input / $5 output) ---
    "claude-haiku-4-5-20251001": {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    "claude-haiku-4-5":          {"input":  1.00, "output":  5.00, "cache_read": 0.10,  "cache_write":  1.25, "cache_write_1h":  2.00},
    # --- Haiku 3.5 (older, cheaper input) ---
    "claude-3-5-haiku":          {"input":  0.80, "output":  4.00, "cache_read": 0.08,  "cache_write":  1.00, "cache_write_1h":  1.60},
    # --- Opus 3 (deprecated; old-tier rates) ---
    "claude-3-opus":             {"input": 15.00, "output": 75.00, "cache_read": 1.50,  "cache_write": 18.75, "cache_write_1h": 30.00},
    # --- Non-Anthropic models (OpenRouter rates, 2026-04-25; no prompt caching) ---
    # GLM models — Z.ai / Zhipu AI
    "glm-4.7":                   {"input":  0.38, "output":  1.74, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    "glm-5":                     {"input":  0.60, "output":  2.08, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
    "glm-5.1":                   {"input":  1.05, "output":  3.50, "cache_read": 0.00, "cache_write": 0.00, "cache_write_1h": 0.00},
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
    # ----- Opus 4.0 (anchored regex; replaces the prefix-fallback `claude-opus-4`
    # entry that was removed in v1.41.2). Without this anchored form, the bare
    # `claude-opus-4` prefix in `_PRICING` would silently catch any future
    # `claude-opus-4-N` (N >= 8 — see _PRICING_FAMILY_FALLBACKS below) and
    # over-charge by 3x at OLD-tier $15/$75. Match policy: the bare ID
    # `claude-opus-4` OR a single date-suffixed form `claude-opus-4-YYYYMMDD`
    # (8 digits). Anything else (e.g. `claude-opus-4-1-...`, `claude-opus-4-8`)
    # is left to fall through to a more-specific entry or the family fallback.
    (re.compile(r"^claude-opus-4(?:-\d{8})?$",       re.I),
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
_PRICING_FAMILY_FALLBACKS: list[tuple[re.Pattern[str], dict[str, float]]] = [
    # Future Opus 4 minors without an explicit key. Anthropic minor versions
    # are single-digit; `claude-opus-4-5/4-6/4-7/4-8` are explicit keys (caught
    # by exact match before this fires), so this now back-stops a hypothetical
    # `claude-opus-4-9`. The trailing `(?:-|$)` lets it match date-suffixed
    # forms like `claude-opus-4-9-20260601` while rejecting 2-digit accidents
    # (`claude-opus-4-99` would fall through and warn, but `claude-opus-4-5x`
    # would not match here).
    (re.compile(r"^claude-opus-4-[5-9](?:-|$)",            re.I), _PRICING["claude-opus-4-7"]),
    # Future Opus majors (5+). New tier is the conservative bet — under-
    # counting by ~10% if Anthropic raises Opus 5 prices is much better
    # than the previous 3x silent overcharge from the OLD-tier prefix.
    (re.compile(r"^claude-opus-(?:[5-9]|\d{2,})(?:-|$)",   re.I), _PRICING["claude-opus-4-7"]),
    # Future Haiku 4 minors (4-6+). `claude-haiku-4-5*` are explicit
    # exact keys and short-circuit before reaching here.
    (re.compile(r"^claude-haiku-4-[6-9](?:-|$)",           re.I), _PRICING["claude-haiku-4-5"]),
    # Future Haiku majors (5+). Same conservative-bet reasoning as Opus.
    (re.compile(r"^claude-haiku-(?:[5-9]|\d{2,})(?:-|$)",  re.I), _PRICING["claude-haiku-4-5"]),
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
        print(
            f"[note] {n} fast-mode turn{'s' if n != 1 else ''} detected; "
            "cost shown is base-rate × 1.0 (actual is ~6×). "
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
del _ch_m

_tp_m = _load_leaf("_turn_parser")
_EXIT_CMD_MARKER              = _tp_m._EXIT_CMD_MARKER
_CONTINUE_FROM_RESUME_MARKER  = _tp_m._CONTINUE_FROM_RESUME_MARKER
_RESUME_LOOKBACK_USER_ENTRIES = _tp_m._RESUME_LOOKBACK_USER_ENTRIES
_resume_fingerprint_match     = _tp_m._resume_fingerprint_match
_extract_turns                = _tp_m._extract_turns
_SLASH_WRAPPED_RE             = _tp_m._SLASH_WRAPPED_RE
_SLASH_BARE_RE                = _tp_m._SLASH_BARE_RE
_XML_MARKER_RE                = _tp_m._XML_MARKER_RE
_ASSISTANT_TEXT_CAP           = _tp_m._ASSISTANT_TEXT_CAP
_PROMPT_TEXT_CAP              = _tp_m._PROMPT_TEXT_CAP
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
_build_usage_insights_md        = _mr_m._build_usage_insights_md
_build_waste_analysis_md        = _mr_m._build_waste_analysis_md
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
_SUBAGENT_FILENAME_RE           = _di_m._SUBAGENT_FILENAME_RE
_resolve_subagent_type          = _di_m._resolve_subagent_type
_load_session                   = _di_m._load_session
_run_single_session             = _di_m._run_single_session
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
_build_hour_of_day_html         = _hs_m._build_hour_of_day_html
_build_punchcard_html           = _hs_m._build_punchcard_html
_tz_dropdown_options            = _hs_m._tz_dropdown_options
_build_tod_heatmap_html         = _hs_m._build_tod_heatmap_html
_fmt_cost                       = _hs_m._fmt_cost
_build_by_skill_html            = _hs_m._build_by_skill_html
_build_by_subagent_type_html    = _hs_m._build_by_subagent_type_html
_build_subagent_share_card_html = _hs_m._build_subagent_share_card_html
_build_subagent_turn_share_card_html = _hs_m._build_subagent_turn_share_card_html
_build_plan_leverage_card_html  = _hs_m._build_plan_leverage_card_html
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
_build_chartrail_section_html   = _hs_m._build_chartrail_section_html
_chartrail_script               = _hs_m._chartrail_script
_build_daily_cost_rail_html     = _hs_m._build_daily_cost_rail_html
_daily_cost_rail_script         = _hs_m._daily_cost_rail_script
render_html                     = _hs_m.render_html
del _hs_m

_rp_m = _load_leaf("_report")
_compute_subagent_share             = _rp_m._compute_subagent_share
_compute_within_session_split       = _rp_m._compute_within_session_split
_compute_window_stats               = _rp_m._compute_window_stats
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
_SELF_COST_SKILL_NAMES      = _da_m._SELF_COST_SKILL_NAMES
_summarize_self_cost        = _da_m._summarize_self_cost
_empty_subagent_row         = _da_m._empty_subagent_row
_finalise_subagent_rows     = _da_m._finalise_subagent_rows
_build_by_subagent_type     = _da_m._build_by_subagent_type
_write_evidence_pack        = _da_m._write_evidence_pack
del _da_m

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
