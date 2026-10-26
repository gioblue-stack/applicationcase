"""Внеплановая проверка по косвенным сигналам дневника (компонент 4 §4.6).

Приложение предлагает уточняющий блок раньше еженедельного опросника. Это предложение,
а не флаг: флаг появится по ответам блока. Триггеры, связанные с лечением
(старт/смена дозы, самостоятельная отмена), добавляются вместе со схемой лечения.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.enums import RiskTrigger

# Для «среднего за предыдущую неделю» нужно хотя бы столько дней с отметкой настроения,
# иначе среднее по 1–2 дням случайно. Порог не задан в Положении — требует утверждения врачами.
MIN_DAYS_FOR_WEEK_MEAN = 3


@dataclass(frozen=True)
class DayVitals:
    mood: int | None
    anxiety: int | None
    sleep_hours: float | None


def _consecutive(by_day: Mapping[date, DayVitals], day: date, days: int, predicate) -> bool:
    for k in range(days):
        vitals = by_day.get(day - timedelta(days=k))
        if vitals is None or not predicate(vitals):
            return False
    return True


def treatment_change_block_due(
    change_dates: list[date], last_block: date | None, today: date, *, every_days: int, window_days: int
) -> bool:
    """После старта антидепрессанта или смены дозы блок предлагается чаще (§4.6 к. 4, В5):
    раз в every_days дней в течение window_days дней после изменения."""
    if not any(0 <= (today - d).days < window_days for d in change_dates):
        return False
    return last_block is None or (today - last_block).days >= every_days


def diary_triggers(by_day: Mapping[date, DayVitals], day: date, t: Mapping[str, float]) -> list[RiskTrigger]:
    triggers: list[RiskTrigger] = []
    today = by_day.get(day)
    if today is None:
        return triggers

    previous = [
        v.mood
        for k in range(1, 8)
        if (v := by_day.get(day - timedelta(days=k))) is not None and v.mood is not None
    ]
    if (
        today.mood is not None
        and len(previous) >= MIN_DAYS_FOR_WEEK_MEAN
        and sum(previous) / len(previous) - today.mood >= t["unscheduled_mood_drop_vs_prev_week_mean"]
    ):
        triggers.append(RiskTrigger.UNSCHEDULED_MOOD_DROP)

    if _consecutive(
        by_day, day, int(t["unscheduled_very_low_mood_days"]),
        lambda v: v.mood is not None and v.mood <= t["unscheduled_very_low_mood_max"],
    ):
        triggers.append(RiskTrigger.UNSCHEDULED_VERY_LOW_MOOD)

    if _consecutive(
        by_day, day, int(t["unscheduled_insomnia_nights"]),
        lambda v: v.sleep_hours is not None and v.anxiety is not None
        and v.sleep_hours < t["unscheduled_insomnia_sleep_hours_below"]
        and v.anxiety >= t["unscheduled_insomnia_anxiety_min"],
    ):
        triggers.append(RiskTrigger.UNSCHEDULED_INSOMNIA_ANXIETY)

    return triggers
