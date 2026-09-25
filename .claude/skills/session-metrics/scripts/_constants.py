"""Shared literals consumed at function-def time.

Constants imported here cannot be replaced with `_sm()._NAME` lookups because
they are referenced as default-argument values (`def fn(x: int = _NAME)`),
which Python evaluates at def-time — before `_sm()` (the orchestrator
back-reference) is wired up. Keep this leaf dependency-free so it can be the
first one `session-metrics.py` loads.
"""

# Cache-break threshold: any single turn with
# ``input_tokens + cache_write_tokens > _CACHE_BREAK_DEFAULT_THRESHOLD`` is
# flagged. Matches the Anthropic session-report default. Override via
# ``--cache-break-threshold`` on the CLI; runtime reads in function bodies
# go through ``_sm()._CACHE_BREAK_DEFAULT_THRESHOLD`` so tests can monkeypatch.
_CACHE_BREAK_DEFAULT_THRESHOLD = 100_000

# Per-model context-window sizes (tokens), used by the session-health
# context-pressure signal (peak per-turn context ÷ window). Matched by
# LONGEST-PREFIX first so a specific key wins over a generic family prefix.
# Opus/Sonnet/Haiku base windows are 200K; their 1M long-context tier is
# detected separately via a ``[1m]`` suffix on the model id
# (``_context_window_for``), so it overrides regardless of which family key
# matched. Fable (5 / 5.1) ships with 1M as its DEFAULT window and Claude Code
# stamps it WITHOUT a ``[1m]`` tag (live transcripts peak at 480K–640K context
# on bare ``claude-fable-5`` / ``claude-fable-5-1``), so the family key itself
# carries 1M (v1.88.0) — at 200K the context-pressure signal exceeded 100%.
# Opus 5 / 5.5 are the same: 1M is their only window and Claude Code stamps
# bare ``claude-opus-5`` / ``claude-opus-5-5`` (v1.90.2); the longer prefix
# wins over ``claude-opus``.
_MODEL_CONTEXT_WINDOWS = {
    "claude-opus":   200_000,
    "claude-opus-5": 1_000_000,
    "claude-sonnet": 200_000,
    "claude-haiku":  200_000,
    "claude-fable":  1_000_000,
}
_DEFAULT_CONTEXT_WINDOW = 200_000
_LONG_CONTEXT_WINDOW = 1_000_000
