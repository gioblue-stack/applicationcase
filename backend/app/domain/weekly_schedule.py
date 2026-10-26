"""График PHQ-9 + GAD-7 раз в 7 дней (§4.2): повтор напоминания через 1 день, пропуск через 3."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.domain.enums import ScheduleStatus


def due_date_for(anchor: date, today: date) -> date | None:
    """Последний срок не позже сегодняшнего. Первый опросник — в день подключения к врачу."""
    if today < anchor:
        return None
    return anchor + timedelta(days=7 * ((today - anchor).days // 7))


def slot_transition(
    status: ScheduleStatus, due: date, today: date, *, remind_after_days: int, missed_after_days: int
) -> ScheduleStatus:
    if status in (ScheduleStatus.DONE, ScheduleStatus.MISSED):
        return status
    overdue = (today - due).days
    if overdue >= missed_after_days:
        return ScheduleStatus.MISSED
    if overdue >= remind_after_days:
        return ScheduleStatus.REMINDED
    return status


def next_self_check_at(last_self_check_at: datetime | None, *, min_interval_days: int) -> datetime | None:
    """Самопроверка не чаще раза в 14 дней: оба опросника спрашивают о двух неделях (§3.1)."""
    if last_self_check_at is None:
        return None
    return last_self_check_at + timedelta(days=min_interval_days)
