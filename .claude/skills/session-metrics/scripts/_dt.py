"""General-purpose datetime utility for session-metrics."""
from datetime import UTC, date, datetime


def _parse_iso_dt(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp to a tz-aware ``datetime``; ``None`` on failure.

    Catches the union of error types historically swallowed at every call
    site so each caller's existing safety net is preserved unchanged.
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError, OSError):
        return None


def _effective_date(ts: str | None) -> date | None:
    """UTC calendar date of a turn's ISO-8601 timestamp, for date-effective pricing.

    Returns ``None`` when the timestamp is missing, unparseable, OR
    timezone-naive. A naive stamp has no defined UTC date without assuming the
    host timezone — doing so would make the computed cost machine-dependent —
    so we treat it as "unknown date" and let the pricing layer fall back to the
    standard (non-introductory) rate. That fallback is the conservative choice:
    an unknown-date turn is never under-priced against a limited-time discount.
    """
    dt = _parse_iso_dt(ts) if ts else None
    if dt is None or dt.tzinfo is None:
        return None
    return dt.astimezone(UTC).date()
