from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.domain.notifications import in_interval, parse_hhmm, postpone_into, postpone_out_of

MSK = ZoneInfo("Europe/Moscow")


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=MSK)


@pytest.mark.parametrize(
    ("t", "start", "end", "inside"),
    [(time(23, 30), time(23), time(8), True), (time(7, 59), time(23), time(8), True),
     (time(8), time(23), time(8), False), (time(12), time(9), time(18), True), (time(18), time(9), time(18), False),
     (time(12), time(9), time(9), False)],
)
def test_in_interval_including_overnight(t, start, end, inside):
    assert in_interval(t, start, end) is inside


@pytest.mark.parametrize(
    ("now", "expected"),
    [(at(26, 23, 30), at(27, 8)), (at(27, 7), at(27, 8)), (at(26, 12), None)],
)
def test_quiet_hours_postpone_to_their_end(now, expected):
    assert postpone_out_of(now, time(23), time(8)) == expected


@pytest.mark.parametrize(
    ("now", "expected"),
    [(at(26, 23), at(27, 8)), (at(27, 6), at(27, 8)), (at(26, 10), None)],
)
def test_doctor_window_postpones_to_its_start(now, expected):
    assert postpone_into(now, time(8), time(22)) == expected


def test_empty_window_means_always():
    assert postpone_into(at(26, 3), time(0), time(0)) is None


def test_parse_hhmm():
    assert parse_hhmm("08:30") == time(8, 30)
