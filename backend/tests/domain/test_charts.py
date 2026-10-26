from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.charts import adherence_summary, diary_series, effective_dose_status
from app.domain.enums import DoseStatus, MedsTaken

D = DoseStatus
START = date(2026, 10, 20)


@dataclass
class Row:
    mood: int | None = None
    interest: int | None = None
    anxiety: int | None = None
    worry_control: int | None = None
    sleep_hours: Decimal | None = None
    sleep_quality: int | None = None
    energy: int | None = None
    meds_taken: MedsTaken | None = None
    had_side_effects: bool | None = None
    filled_late: bool = False


def test_missing_days_and_skipped_questions_are_null_not_zero():
    entries = {START: Row(mood=0, sleep_hours=Decimal("7.5"), meds_taken=MedsTaken.ALL),
               START + timedelta(days=2): Row(mood=6, filled_late=True)}
    series = diary_series(entries, START, START + timedelta(days=3))
    assert series.days == [START + timedelta(days=i) for i in range(4)]
    assert series.values["mood"] == [0, None, 6, None]  # 0 — «очень плохое», None — пропуск
    assert series.values["sleep_hours"] == [7.5, None, None, None]
    assert series.values["anxiety"] == [None, None, None, None]
    assert series.meds_taken == ["all", None, None, None]
    assert series.filled_late == [False, None, True, None]
    assert series.filled_days == 2


NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("status", "ago", "expected"),
    [(D.TAKEN, timedelta(hours=5), D.TAKEN), (D.PENDING, timedelta(hours=1), None),
     (D.PENDING, timedelta(hours=3), D.NO_RESPONSE), (D.PENDING, -timedelta(hours=1), None),
     (D.MISSED, timedelta(days=2), D.MISSED)],
)
def test_effective_dose_status(status, ago, expected):
    assert effective_dose_status(status, NOW - ago, NOW, no_response_hours=3) == expected


def test_adherence_counts_unknown_separately():
    summary = adherence_summary([D.TAKEN, D.TAKEN_LATE, D.MISSED, D.SELF_CHANGED, D.NO_RESPONSE, D.TAKEN, D.TAKEN])
    assert (summary.due, summary.taken, summary.taken_late, summary.missed, summary.self_changed,
            summary.no_response) == (7, 3, 1, 1, 1, 1)
    assert summary.taken_percent == 57.1


def test_adherence_without_due_doses_has_no_percent():
    assert adherence_summary([]).taken_percent is None
