from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import get_settings

# Fallback when tzdata is not installed (common on Windows before pip install tzdata).
IST = timezone(timedelta(hours=5, minutes=30))


@lru_cache
def get_snapshot_tz():
    name = get_settings().snapshot_tz
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Asia/Kolkata":
            return IST
        raise


@lru_cache
def get_snapshot_at() -> datetime:
    """Authoritative assessment clock (timezone-aware)."""
    return datetime.fromisoformat(get_settings().snapshot_at)


def parse_assessment_datetime(value: datetime | str | None) -> datetime | None:
    """Parse Excel/datetime values as assessment-local time (Asia/Kolkata)."""
    if value is None:
        return None
    tz = get_snapshot_tz()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz)
        return value.astimezone(tz)
    text = str(value).strip()
    if not text:
        return None
    # README uses "2026-08-16 11:00 Asia/Kolkata"
    if " Asia/Kolkata" in text:
        text = text.replace(" Asia/Kolkata", "").strip()
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)
