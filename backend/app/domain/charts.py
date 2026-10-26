"""Данные для графиков карточки врача (§1.1, §1.2).

Пропущенный день — пропуск, а не ноль: в рядах на его месте None, и график рисует разрыв линии.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.enums import DoseStatus

DIARY_METRICS = ("mood", "interest", "anxiety", "worry_control", "sleep_hours", "sleep_quality", "energy")


@dataclass(frozen=True)
class DiarySeries:
    days: list[date]
    values: dict[str, list[float | None]]
    meds_taken: list[str | None]
    had_side_effects: list[bool | None]
    filled_late: list[bool | None]
    filled_days: int


def diary_series(entries_by_day: Mapping[date, object], start: date, end: date) -> DiarySeries:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    rows = [entries_by_day.get(d) for d in days]

    def column(name: str) -> list:
        values = [getattr(r, name) if r is not None else None for r in rows]
        return [float(v) if name == "sleep_hours" and v is not None else v for v in values]

    return DiarySeries(
        days=days,
        values={m: column(m) for m in DIARY_METRICS},
        meds_taken=[(r.meds_taken.value if r.meds_taken else None) if r is not None else None for r in rows],
        had_side_effects=column("had_side_effects"),
        filled_late=column("filled_late"),
        filled_days=sum(r is not None for r in rows),
    )


TAKEN = {DoseStatus.TAKEN, DoseStatus.TAKEN_LATE}


def effective_dose_status(status: DoseStatus, scheduled_at: datetime, now: datetime, *, no_response_hours: int
                          ) -> DoseStatus | None:
    """Статус для статистики. None — приём ещё не наступил или пациент ещё может ответить вовремя."""
    if scheduled_at > now:
        return None
    if status is DoseStatus.PENDING:
        return DoseStatus.NO_RESPONSE if now - scheduled_at >= timedelta(hours=no_response_hours) else None
    return status


@dataclass(frozen=True)
class AdherenceSummary:
    due: int
    taken: int
    taken_late: int
    missed: int
    self_changed: int
    no_response: int
    taken_percent: float | None  # доля принятых (вовремя и позже) среди наступивших приёмов


def adherence_summary(statuses: Iterable[DoseStatus]) -> AdherenceSummary:
    """«Нет ответа» входит в знаменатель как неподтверждённый приём, но показывается отдельно:
    это «не знаем», а не «пропустил» (§1.2)."""
    counts = {s: 0 for s in DoseStatus}
    for s in statuses:
        counts[s] += 1
    due = sum(counts[s] for s in (DoseStatus.TAKEN, DoseStatus.TAKEN_LATE, DoseStatus.MISSED,
                                  DoseStatus.SELF_CHANGED, DoseStatus.NO_RESPONSE))
    taken = counts[DoseStatus.TAKEN] + counts[DoseStatus.TAKEN_LATE]
    return AdherenceSummary(
        due=due, taken=counts[DoseStatus.TAKEN], taken_late=counts[DoseStatus.TAKEN_LATE],
        missed=counts[DoseStatus.MISSED], self_changed=counts[DoseStatus.SELF_CHANGED],
        no_response=counts[DoseStatus.NO_RESPONSE],
        taken_percent=round(100 * taken / due, 1) if due else None,
    )
