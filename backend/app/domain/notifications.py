"""Когда можно отправлять уведомление (§5.3).

Пациент выбирает «тихие часы»: в них не приходят напоминания о дневнике и опросниках,
но напоминания о приёме лекарств приходят всё равно. Врач выбирает, в какое время получать
push о флагах; вне этого окна push откладывается (флаг в кабинете виден сразу).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta


def in_interval(t: time, start: time, end: time) -> bool:
    """Интервал [start, end) с переходом через полночь (22:00–08:00)."""
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


def postpone_out_of(now_local: datetime, start: time, end: time) -> datetime | None:
    """Если сейчас внутри запрещённого интервала — момент его окончания, иначе None."""
    if not in_interval(now_local.time(), start, end):
        return None
    until = datetime.combine(now_local.date(), end, tzinfo=now_local.tzinfo)
    if until <= now_local:
        until += timedelta(days=1)
    return until


def postpone_into(now_local: datetime, allowed_start: time, allowed_end: time) -> datetime | None:
    """Разрешённое окно врача: всё вне [allowed_start, allowed_end) откладывается до начала окна."""
    if allowed_start == allowed_end:
        return None
    return postpone_out_of(now_local, allowed_end, allowed_start)


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))
