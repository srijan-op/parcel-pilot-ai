from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.timeutil import get_snapshot_at, parse_assessment_datetime


def test_snapshot_at_is_timezone_aware() -> None:
    snapshot = get_snapshot_at()
    assert snapshot.tzinfo is not None
    assert snapshot.year == 2026
    assert snapshot.month == 8
    assert snapshot.day == 16
    assert snapshot.hour == 11


def test_parse_naive_excel_datetime() -> None:
    tz = ZoneInfo("Asia/Kolkata")
    parsed = parse_assessment_datetime("2026-08-16 09:00")
    assert parsed is not None
    assert parsed.tzinfo == tz
    assert parsed.hour == 9


def test_parse_datetime_object() -> None:
    naive = datetime(2026, 8, 16, 10, 30)
    parsed = parse_assessment_datetime(naive)
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.hour == 10


def test_parse_none() -> None:
    assert parse_assessment_datetime(None) is None
