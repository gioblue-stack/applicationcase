"""Схема лечения, титрация, отметки о приёме и правило при пропуске (§1.2, §1.3, §2.2).

Схема — продолжение назначений очного приёма. Сдвиг этапов титрации — только ручное решение
врача: программа не сдвигает этапы сама ни при каких пропусках (§1.3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.domain.enums import DoseStatus, MissedDoseRule

MAX_SHIFT_DAYS = 60
MAX_MISSED_DOSE_HOURS = 48
# Отметить приём можно чуть раньше назначенного времени: таблетку часто пьют до напоминания.
EARLY_MARK = timedelta(minutes=60)


class InvalidRegimen(ValueError):
    pass


class InvalidDoseResponse(ValueError):
    pass


@dataclass(frozen=True)
class Step:
    effective_date: date
    dose: Decimal


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def validate_regimen(
    *,
    dose,
    times: Sequence[time],
    start_date: date,
    end_date: date | None,
    in_person_visit_date: date,
    missed_dose_rule: MissedDoseRule,
    missed_dose_hours: int | None,
    steps: Sequence[Step],
) -> None:
    if _dec(dose) <= 0:
        raise InvalidRegimen("Доза должна быть больше нуля")
    if not times:
        raise InvalidRegimen("Укажите время приёма")
    if len(set(times)) != len(times):
        raise InvalidRegimen("Время приёма повторяется")
    if in_person_visit_date > start_date:
        # Ст. 36.2 323-ФЗ: схема продолжает назначения очного приёма, а не заменяет его.
        raise InvalidRegimen("Назначение начинается после очного приёма")
    if end_date is not None and end_date < start_date:
        raise InvalidRegimen("Дата окончания раньше даты начала")
    if missed_dose_rule is MissedDoseRule.TAKE_IF_MORE_THAN_HOURS:
        if missed_dose_hours is None or not 1 <= missed_dose_hours <= MAX_MISSED_DOSE_HOURS:
            raise InvalidRegimen(
                f"Для правила «принять, если до следующего приёма больше N часов» нужно N от 1 до {MAX_MISSED_DOSE_HOURS}"
            )
    elif missed_dose_hours is not None:
        raise InvalidRegimen("Число часов задаётся только для правила «принять, если до следующего приёма больше N часов»")
    validate_steps(steps, start_date=start_date, end_date=end_date)


def validate_steps(steps: Sequence[Step], *, start_date: date, end_date: date | None) -> None:
    dates = [s.effective_date for s in steps]
    if len(set(dates)) != len(dates):
        raise InvalidRegimen("Два этапа титрации на одну дату")
    for s in steps:
        if s.effective_date <= start_date:
            raise InvalidRegimen("Этап титрации должен начинаться после даты начала приёма")
        if end_date is not None and s.effective_date > end_date:
            raise InvalidRegimen("Этап титрации после окончания приёма")
        if _dec(s.dose) <= 0:
            raise InvalidRegimen("Доза этапа должна быть больше нуля")


def dose_on(day: date, base_dose, steps: Sequence[Step]) -> Decimal:
    current = _dec(base_dose)
    for s in sorted(steps, key=lambda s: s.effective_date):
        if s.effective_date <= day:
            current = _dec(s.dose)
    return current


def planned_doses(
    *,
    start_date: date,
    end_date: date | None,
    times: Sequence[time],
    timezone: str,
    base_dose,
    steps: Sequence[Step],
    window_from: datetime,
    window_to: datetime,
) -> list[tuple[datetime, Decimal]]:
    """Приёмы по расписанию в окне [window_from, window_to). Время — в таймзоне пациента, результат — UTC."""
    tz = ZoneInfo(timezone)
    first = max(start_date, window_from.astimezone(tz).date())
    last = window_to.astimezone(tz).date()
    if end_date is not None:
        last = min(last, end_date)
    result = []
    day = first
    while day <= last:
        for t in sorted(times):
            at = datetime.combine(day, t, tzinfo=tz).astimezone(UTC)
            if window_from <= at < window_to:
                result.append((at, dose_on(day, base_dose, steps)))
        day += timedelta(days=1)
    return result


def shift_future_steps(steps: Sequence[Step], *, today: date, days: int) -> list[Step]:
    """Кнопка врача «Сдвинуть следующие этапы на N дней». Уже начавшиеся этапы не трогаются."""
    if not 1 <= days <= MAX_SHIFT_DAYS:
        raise InvalidRegimen(f"Сдвиг — от 1 до {MAX_SHIFT_DAYS} дней")
    if not any(s.effective_date > today for s in steps):
        raise InvalidRegimen("Нет предстоящих этапов титрации")
    return [replace(s, effective_date=s.effective_date + timedelta(days=days)) if s.effective_date > today else s
            for s in steps]


def upcoming_steps(steps: Sequence[Step], today: date) -> list[Step]:
    return sorted((s for s in steps if s.effective_date > today), key=lambda s: s.effective_date)


def format_dose(value) -> str:
    text = format(_dec(value).normalize(), "f")
    return text.replace(".", ",")


def format_step(template: str, step: Step, unit: str) -> str:
    """«с 20.09.2027 — 100 мг» (§2.2)."""
    return template.format(date=step.effective_date.strftime("%d.%m.%Y"), dose=format_dose(step.dose), unit=unit)


# --- Отметки о приёме ------------------------------------------------------------------------


class DoseResponse(StrEnum):
    TAKEN = "taken"
    TAKEN_LATE = "taken_late"
    MISSED = "missed"
    SELF_CHANGED = "self_changed"


_RESPONSE_STATUS = {
    DoseResponse.TAKEN: DoseStatus.TAKEN,
    DoseResponse.TAKEN_LATE: DoseStatus.TAKEN_LATE,
    DoseResponse.MISSED: DoseStatus.MISSED,
    DoseResponse.SELF_CHANGED: DoseStatus.SELF_CHANGED,
}
# «Нет ответа» — не окончательный статус: пациент может отметить приём позже (В4).
ANSWERABLE = {DoseStatus.PENDING, DoseStatus.NO_RESPONSE}


def apply_response(
    *, current: DoseStatus, scheduled_at: datetime, now: datetime, response: DoseResponse,
    planned_dose, actual_dose=None,
) -> tuple[DoseStatus, Decimal | None]:
    if current not in ANSWERABLE:
        raise InvalidDoseResponse("Этот приём уже отмечен")
    if now < scheduled_at - EARLY_MARK:
        raise InvalidDoseResponse("Время этого приёма ещё не пришло")
    if response is DoseResponse.SELF_CHANGED:
        if actual_dose is None or _dec(actual_dose) <= 0:
            raise InvalidDoseResponse("Укажите, какую дозу вы приняли")
        if _dec(actual_dose) == _dec(planned_dose):
            raise InvalidDoseResponse("Доза совпадает с назначенной — отметьте «Принял(а)»")
        return DoseStatus.SELF_CHANGED, _dec(actual_dose)
    if actual_dose is not None:
        raise InvalidDoseResponse("Доза указывается только при самостоятельном изменении")
    return _RESPONSE_STATUS[response], None


def no_response_due(status: DoseStatus, scheduled_at: datetime, now: datetime, *, hours: int) -> bool:
    return status is DoseStatus.PENDING and now - scheduled_at >= timedelta(hours=hours)


class MissedDoseHint(StrEnum):
    TAKE_NOW = "take_now"
    SKIP_NOW = "skip_now"


def missed_dose_hint(
    rule: MissedDoseRule, hours: int | None, *, now: datetime, next_dose_at: datetime | None
) -> MissedDoseHint | None:
    """Подсказка по правилу врача «принять, если до следующего приёма больше N часов».

    Для остальных правил подсказки нет — показывается само правило. Двойная доза не советуется никогда.
    """
    if rule is not MissedDoseRule.TAKE_IF_MORE_THAN_HOURS:
        return None
    assert hours is not None
    if next_dose_at is None or next_dose_at - now > timedelta(hours=hours):
        return MissedDoseHint.TAKE_NOW
    return MissedDoseHint.SKIP_NOW
