"""Date/time normalization for Play scraper output and CSV imports.

All datetimes are stored as UTC-naive in SQLite; display filters convert to local time.
"""

from datetime import datetime, timezone


def coerce_review_datetime(value) -> datetime | None:
    """Accept datetime, epoch seconds/ms, or ISO strings; always return UTC-naive."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, (int, float)):
        try:
            ts = float(value)
            if ts > 1e12:
                ts /= 1000.0
            return datetime.utcfromtimestamp(ts)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            return None
    return None


def normalize_play_review_at(value) -> datetime | None:
    """google-play-scraper uses fromtimestamp (naive local); store UTC naive."""
    dt = coerce_review_datetime(value)
    if dt is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is None:
        return datetime.utcfromtimestamp(value.timestamp())
    return dt


def parse_csv_review_date(row: dict) -> datetime | None:
    return coerce_review_datetime(
        row.get("at") or row.get("reviewed_at") or row.get("date") or row.get("review_date")
    )


def utc_naive_to_local(dt: datetime | None) -> datetime | None:
    """Template filter helper: treat stored naive values as UTC, show in server local TZ."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
