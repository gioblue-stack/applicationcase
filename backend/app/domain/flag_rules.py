"""Правила флагов срочности (§1.1, §7.2). Чистые функции: данные на входе, решение на выходе.

Пороги приходят параметрами из настроек (content/thresholds.json + переопределения в БД),
в коде их нет.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum

from app.domain.enums import DoseStatus, FlagLevel, FlagReason, InstrumentCode


@dataclass(frozen=True)
class FlagCandidate:
    level: FlagLevel
    reason: FlagReason
    dedupe_key: str
    details: dict = field(default_factory=dict)


# --- Опросники -------------------------------------------------------------------------------

_INCREASE_REASON = {InstrumentCode.PHQ9: FlagReason.PHQ9_INCREASE, InstrumentCode.GAD7: FlagReason.GAD7_INCREASE}


def score_increase(
    instrument: InstrumentCode, *, previous_total: int | None, new_total: int, threshold: int, submission_id: object
) -> FlagCandidate | None:
    """Рост суммы на клинически значимую величину к прошлому заполнению: PHQ-9 ≥ 5, GAD-7 ≥ 4."""
    if previous_total is None or new_total - previous_total < threshold:
        return None
    return FlagCandidate(
        FlagLevel.YELLOW,
        _INCREASE_REASON[instrument],
        f"{_INCREASE_REASON[instrument].value}:{submission_id}",
        {"previous": previous_total, "current": new_total},
    )


# --- Приём препаратов ------------------------------------------------------------------------

# «Нет ответа» — это «не знаем», а не пропуск (§1.2): не считается и серию не прерывает.
_NEUTRAL = {DoseStatus.PENDING, DoseStatus.NO_RESPONSE}


def consecutive_missed(statuses_oldest_first: Sequence[DoseStatus]) -> int:
    count = 0
    for status in reversed(statuses_oldest_first):
        if status in _NEUTRAL:
            continue
        if status is not DoseStatus.MISSED:
            break
        count += 1
    return count


def missed_doses(
    statuses_oldest_first: Sequence[DoseStatus], *, threshold: int, prescription_id: object
) -> FlagCandidate | None:
    count = consecutive_missed(statuses_oldest_first)
    if count < threshold:
        return None
    return FlagCandidate(
        FlagLevel.YELLOW, FlagReason.MISSED_DOSES, f"missed_doses:{prescription_id}", {"in_row": count}
    )


def self_dose_change(source: str, source_id: object) -> FlagCandidate:
    return FlagCandidate(FlagLevel.YELLOW, FlagReason.SELF_DOSE_CHANGE, f"self_dose_change:{source}:{source_id}")


# --- Дневник ---------------------------------------------------------------------------------


def low_mood_streak(moods_by_day: Mapping[date, int | None], day: date, *, max_mood: int, days: int) -> bool:
    """Настроение ≤ max_mood N календарных дней подряд. Пропущенный день рвёт серию — это не 0."""
    for k in range(days):
        mood = moods_by_day.get(day - timedelta(days=k))
        if mood is None or mood > max_mood:
            return False
    return True


def low_mood(moods_by_day: Mapping[date, int | None], day: date, *, max_mood: int, days: int) -> FlagCandidate | None:
    if not low_mood_streak(moods_by_day, day, max_mood=max_mood, days=days):
        return None
    return FlagCandidate(FlagLevel.YELLOW, FlagReason.LOW_MOOD_STREAK, "low_mood_streak", {"until": day.isoformat()})


def side_effect_key(code: str, other_text: str | None) -> str:
    """«Новый» эффект — новый код; для «Другое» — новый текст."""
    if code != "other" or not other_text:
        return code
    return "other:" + " ".join(other_text.lower().replace("ё", "е").split())[:80]


def new_side_effect(code: str, other_text: str | None, *, known_keys: Iterable[str]) -> FlagCandidate | None:
    key = side_effect_key(code, other_text)
    if key in set(known_keys):
        return None
    return FlagCandidate(FlagLevel.YELLOW, FlagReason.NEW_SIDE_EFFECT, f"new_side_effect:{key}", {"code": code})


# --- Наблюдение ------------------------------------------------------------------------------


def no_data(last_activity: date, today: date, *, days: int) -> FlagCandidate | None:
    """Пациент «выпал» из наблюдения: нет никаких данных N дней."""
    if (today - last_activity).days < days:
        return None
    return FlagCandidate(FlagLevel.YELLOW, FlagReason.NO_DATA, "no_data", {"last_activity": last_activity.isoformat()})


# --- Очередь врача ---------------------------------------------------------------------------


class PatientColor(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


def patient_color(open_flag_levels: Iterable[FlagLevel]) -> PatientColor:
    levels = set(open_flag_levels)
    if FlagLevel.RED in levels:
        return PatientColor.RED
    if FlagLevel.YELLOW in levels:
        return PatientColor.YELLOW
    return PatientColor.GREEN


_COLOR_RANK = {PatientColor.RED: 0, PatientColor.YELLOW: 1, PatientColor.GREEN: 2}


def queue_sort_key(color: PatientColor, latest_open_flag_at: datetime | None) -> tuple[int, float]:
    """Сверху красные, внутри цвета — самые свежие сигналы (§1.1: очередь, а не алфавит)."""
    return (_COLOR_RANK[color], -(latest_open_flag_at.timestamp() if latest_open_flag_at else 0.0))
