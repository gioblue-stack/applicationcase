from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain import flag_rules
from app.domain.enums import DoseStatus, FlagLevel, FlagReason, InstrumentCode
from app.domain.flag_rules import PatientColor

D = DoseStatus
DAY = date(2026, 10, 26)


@pytest.mark.parametrize(
    ("instrument", "previous", "new", "threshold", "flagged"),
    [
        (InstrumentCode.PHQ9, 8, 13, 5, True),
        (InstrumentCode.PHQ9, 8, 12, 5, False),
        (InstrumentCode.PHQ9, 16, 8, 5, False),  # улучшение — не флаг
        (InstrumentCode.PHQ9, None, 27, 5, False),  # первое заполнение — не с чем сравнить
        (InstrumentCode.GAD7, 6, 10, 4, True),
        (InstrumentCode.GAD7, 6, 9, 4, False),
    ],
)
def test_score_increase(instrument, previous, new, threshold, flagged):
    candidate = flag_rules.score_increase(instrument, previous_total=previous, new_total=new,
                                          threshold=threshold, submission_id="s1")
    assert (candidate is not None) == flagged
    if candidate:
        assert candidate.level is FlagLevel.YELLOW
        assert candidate.reason in {FlagReason.PHQ9_INCREASE, FlagReason.GAD7_INCREASE}


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], 0),
        ([D.MISSED], 1),
        ([D.TAKEN, D.MISSED, D.MISSED], 2),
        ([D.MISSED, D.TAKEN], 0),
        ([D.MISSED, D.NO_RESPONSE, D.MISSED], 2),  # «нет ответа» — не пропуск и не перерыв серии
        ([D.MISSED, D.MISSED, D.PENDING], 2),
        ([D.MISSED, D.TAKEN_LATE, D.MISSED], 1),
        ([D.MISSED, D.SELF_CHANGED, D.MISSED], 1),
        ([D.NO_RESPONSE, D.NO_RESPONSE], 0),
    ],
)
def test_consecutive_missed(statuses, expected):
    assert flag_rules.consecutive_missed(statuses) == expected


def test_missed_doses_threshold():
    assert flag_rules.missed_doses([D.MISSED], threshold=2, prescription_id="p") is None
    candidate = flag_rules.missed_doses([D.MISSED, D.MISSED], threshold=2, prescription_id="p")
    assert candidate.dedupe_key == "missed_doses:p"


def _moods(*values):
    """Значения по дням, последнее — DAY."""
    return {DAY - timedelta(days=len(values) - 1 - i): v for i, v in enumerate(values)}


@pytest.mark.parametrize(
    ("moods", "expected"),
    [
        (_moods(3, 2, 3), True),
        (_moods(3, 4, 3), False),
        (_moods(3, 3), False),  # только два дня
        (_moods(3, None, 3), False),  # пропущенный вопрос — не 0 и не «плохо»
        ({DAY: 1, DAY - timedelta(days=1): 1, DAY - timedelta(days=3): 1}, False),  # пропущенный день рвёт серию
        (_moods(5, 0, 0, 0), True),
    ],
)
def test_low_mood_streak(moods, expected):
    assert flag_rules.low_mood_streak(moods, DAY, max_mood=3, days=3) is expected


def test_new_side_effect_by_code_and_by_other_text():
    assert flag_rules.new_side_effect("nausea", None, known_keys={"nausea"}) is None
    assert flag_rules.new_side_effect("headache", None, known_keys={"nausea"}).reason is FlagReason.NEW_SIDE_EFFECT
    known = {flag_rules.side_effect_key("other", "Сухость во рту")}
    assert flag_rules.new_side_effect("other", "сухость  во рту", known_keys=known) is None
    assert flag_rules.new_side_effect("other", "Зуд", known_keys=known) is not None


@pytest.mark.parametrize(("days_ago", "flagged"), [(6, False), (7, True), (30, True)])
def test_no_data(days_ago, flagged):
    assert (flag_rules.no_data(DAY - timedelta(days=days_ago), DAY, days=7) is not None) is flagged


def test_patient_color():
    assert flag_rules.patient_color([]) is PatientColor.GREEN
    assert flag_rules.patient_color([FlagLevel.YELLOW]) is PatientColor.YELLOW
    assert flag_rules.patient_color([FlagLevel.YELLOW, FlagLevel.RED]) is PatientColor.RED


def test_queue_order_is_red_then_yellow_then_green_newest_first():
    t = datetime(2026, 10, 26, tzinfo=UTC)
    patients = {
        "Анна": (PatientColor.GREEN, None),
        "Игорь": (PatientColor.YELLOW, t),
        "Мария": (PatientColor.RED, t - timedelta(hours=5)),
        "Пётр": (PatientColor.RED, t),
    }
    ordered = sorted(patients, key=lambda n: flag_rules.queue_sort_key(*patients[n]))
    assert ordered == ["Пётр", "Мария", "Игорь", "Анна"]
