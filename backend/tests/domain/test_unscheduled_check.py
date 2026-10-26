from datetime import date, timedelta

from app.content.loader import load_content
from app.domain.enums import RiskTrigger
from app.domain.unscheduled_check import DayVitals, diary_triggers

T = load_content().thresholds.values
DAY = date(2026, 10, 26)


def _days(*vitals):
    return {DAY - timedelta(days=len(vitals) - 1 - i): v for i, v in enumerate(vitals) if v is not None}


def v(mood=None, anxiety=None, sleep=None):
    return DayVitals(mood, anxiety, sleep)


def test_mood_drop_against_previous_week_mean():
    history = _days(v(7), v(7), v(6), v(8), v(3))  # среднее 7, сегодня 3 → падение на 4
    assert RiskTrigger.UNSCHEDULED_MOOD_DROP in diary_triggers(history, DAY, T)


def test_mood_drop_below_threshold_is_not_a_trigger():
    history = _days(v(7), v(7), v(7), v(4))
    assert diary_triggers(history, DAY, T) == []


def test_mood_drop_needs_enough_baseline_days():
    history = _days(v(9), v(9), v(2))
    assert RiskTrigger.UNSCHEDULED_MOOD_DROP not in diary_triggers(history, DAY, T)


def test_very_low_mood_three_days():
    assert RiskTrigger.UNSCHEDULED_VERY_LOW_MOOD in diary_triggers(_days(v(2), v(1), v(2)), DAY, T)
    assert RiskTrigger.UNSCHEDULED_VERY_LOW_MOOD not in diary_triggers(_days(v(2), None, v(2), v(2)), DAY, T)


def test_insomnia_with_high_anxiety_three_nights():
    nights = _days(v(anxiety=8, sleep=3.5), v(anxiety=7, sleep=3), v(anxiety=9, sleep=2))
    assert diary_triggers(nights, DAY, T) == [RiskTrigger.UNSCHEDULED_INSOMNIA_ANXIETY]
    calm = _days(v(anxiety=3, sleep=3), v(anxiety=7, sleep=3), v(anxiety=9, sleep=2))
    assert diary_triggers(calm, DAY, T) == []


def test_no_entry_today_no_triggers():
    assert diary_triggers(_days(v(1), v(1), None), DAY, T) == []
