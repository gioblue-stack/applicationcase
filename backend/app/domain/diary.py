"""Ежедневный дневник (§4.3): окно заполнения, проверка ответов, подсказка для вопроса 7."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta
from enum import StrEnum

from app.domain.enums import DoseStatus, MedsTaken

SCALE_FIELDS = ("mood", "interest", "anxiety", "worry_control", "sleep_quality", "energy")


class InvalidDiary(ValueError):
    pass


class DiaryWindow(StrEnum):
    ON_TIME = "on_time"
    LATE = "late"  # «заполнено позже»: вчерашний день до 12:00
    CLOSED = "closed"  # день считается пропущенным


def diary_window(day: date, now_local: datetime, *, cutoff_hour: int) -> DiaryWindow:
    today = now_local.date()
    if day == today:
        return DiaryWindow.ON_TIME
    if day == today - timedelta(days=1) and now_local.hour < cutoff_hour:
        return DiaryWindow.LATE
    return DiaryWindow.CLOSED


@dataclass(frozen=True)
class SideEffectAnswer:
    code: str
    other_text: str | None = None


@dataclass(frozen=True)
class DiaryAnswers:
    """None — вопрос пропущен. Значения по умолчанию у ползунков нет (§4.3)."""

    mood: int | None = None
    interest: int | None = None
    anxiety: int | None = None
    worry_control: int | None = None
    sleep_hours: float | None = None
    sleep_quality: int | None = None
    energy: int | None = None
    meds_taken: MedsTaken | None = None
    had_side_effects: bool | None = None
    side_effects: tuple[SideEffectAnswer, ...] = ()

    def is_empty(self) -> bool:
        return all(getattr(self, f.name) in (None, ()) for f in fields(self))

    def free_texts(self) -> list[str]:
        return [s.other_text for s in self.side_effects if s.other_text]


def validate_diary(
    answers: DiaryAnswers, *, takes_medication: bool, side_effect_codes: Collection[str], max_text: int
) -> None:
    if answers.is_empty():
        raise InvalidDiary("Отметьте хотя бы один пункт")
    for name in SCALE_FIELDS:
        value = getattr(answers, name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10):
            raise InvalidDiary(f"{name}: ожидается целое число от 0 до 10")
    if answers.sleep_hours is not None:
        hours = answers.sleep_hours
        if not 0 <= hours <= 24 or hours * 2 != int(hours * 2):
            raise InvalidDiary("Часы сна: от 0 до 24 с шагом 0,5")

    if not takes_medication:
        # Вопросы 7 и 8 скрываются, если пациент не принимает лекарства.
        if answers.meds_taken is not None or answers.had_side_effects is not None or answers.side_effects:
            raise InvalidDiary("Пациент не принимает лекарства: вопросы 7 и 8 не задаются")
        return

    if answers.had_side_effects is not True and answers.side_effects:
        raise InvalidDiary("Побочные эффекты указаны без ответа «да» на вопрос 8")
    if answers.had_side_effects is True and not answers.side_effects:
        raise InvalidDiary("Выберите, какие неприятные ощущения были")
    codes = [s.code for s in answers.side_effects]
    if len(codes) != len(set(codes)):
        raise InvalidDiary("Побочный эффект указан дважды")
    for s in answers.side_effects:
        if s.code not in side_effect_codes:
            raise InvalidDiary(f"Неизвестный побочный эффект: {s.code}")
        if s.code == "other":
            if not s.other_text or not s.other_text.strip():
                raise InvalidDiary("Опишите, что именно беспокоит")
            if len(s.other_text) > max_text:
                raise InvalidDiary(f"Текст не длиннее {max_text} знаков")
        elif s.other_text:
            raise InvalidDiary("Текст нужен только для варианта «Другое»")


def suggest_meds_taken(statuses: Iterable[DoseStatus]) -> MedsTaken | None:
    """Вопрос 7 заполняется из отметок о приёме; пациент может поправить (§4.3).

    None — недостаточно данных («нет ответа» — это «не знаем», а не «все» и не «пропустил»).
    """
    statuses = list(statuses)
    if DoseStatus.SELF_CHANGED in statuses:
        return MedsTaken.SELF_CHANGED
    if DoseStatus.MISSED in statuses:
        return MedsTaken.MISSED
    if statuses and all(s in (DoseStatus.TAKEN, DoseStatus.TAKEN_LATE) for s in statuses):
        return MedsTaken.ALL
    return None
