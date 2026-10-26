"""Ежедневный дневник (§4.3): сохранение, флаги, кризисные слова, внеплановая проверка (§4.6 к. 4)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.loader import load_content
from app.content.models import Content
from app.domain import flag_rules
from app.domain.crisis_words import CrisisMatcher, default_matcher
from app.domain.diary import DiaryAnswers, DiaryWindow, diary_window, suggest_meds_taken, validate_diary
from app.domain.enums import AuditAction, FlagLevel, FlagReason, MedsTaken, RiskTrigger, SideEffectSource
from app.domain.flag_rules import FlagCandidate
from app.domain.unscheduled_check import DayVitals, diary_triggers
from app.models import DiaryEntry, DiarySideEffect, DoseEvent
from app.services import audit
from app.services.care import active_doctor_id, get_patient, local_now
from app.services.flags import note_patient_activity, raise_flag
from app.services.risk_protocol import assessed_today
from app.services.screens import HelpScreen, help_screen_for
from app.services.side_effects import record_side_effects
from app.services.thresholds import get_thresholds

HISTORY_DAYS = 8  # сегодня + предыдущая неделя: серии и «среднее за неделю»


class DiaryError(ValueError):
    pass


@dataclass(frozen=True)
class DiaryResult:
    entry_id: uuid.UUID
    created: bool
    filled_late: bool
    raised_flags: list[FlagReason]
    help_screen: HelpScreen | None  # кризисные слова в тексте «Другое» → экран помощи сразу (§7.4)
    offer_risk_block: RiskTrigger | None  # внеплановый уточняющий блок


def effective_entries(db: Session, patient_id: uuid.UUID, start: date, end: date) -> dict[date, DiaryEntry]:
    """Последняя версия записи за каждый день: повторное заполнение заменяет, а не удаляет (§1.1)."""
    rows = db.scalars(
        select(DiaryEntry)
        .where(DiaryEntry.patient_id == patient_id, DiaryEntry.day >= start, DiaryEntry.day <= end)
        .order_by(DiaryEntry.submitted_at)
    )
    return {row.day: row for row in rows}


def suggest_meds_taken_for_day(db: Session, patient_id: uuid.UUID, day: date) -> MedsTaken | None:
    """Подсказка для вопроса 7 из отметок о приёме за день (в таймзоне пациента)."""
    patient = get_patient(db, patient_id)
    events = db.scalars(select(DoseEvent).where(DoseEvent.patient_id == patient_id))
    return suggest_meds_taken(e.status for e in events if local_now(patient, e.scheduled_at).date() == day)


def submit_diary(
    db: Session,
    *,
    patient_id: uuid.UUID,
    client_id: uuid.UUID,
    day: date,
    answers: DiaryAnswers,
    client_submitted_at: datetime,
    supersedes_id: uuid.UUID | None = None,
    now: datetime | None = None,
    content: Content | None = None,
    matcher: CrisisMatcher | None = None,
) -> DiaryResult:
    content = content or load_content()
    now = now or datetime.now(UTC)

    existing = db.scalar(select(DiaryEntry).where(DiaryEntry.client_id == client_id))
    if existing is not None:
        if existing.patient_id != patient_id:
            raise DiaryError("client_id уже использован другим пациентом")
        return DiaryResult(existing.id, False, existing.filled_late, [], None, None)

    patient = get_patient(db, patient_id)
    t = get_thresholds(db, content)
    window = diary_window(day, local_now(patient, now), cutoff_hour=int(t["diary_late_fill_until_hour_next_day"]))
    if window is DiaryWindow.CLOSED:
        raise DiaryError("Этот день уже закрыт: запись за него считается пропуском")
    validate_diary(
        answers,
        takes_medication=patient.takes_medication,
        side_effect_codes=content.diary.side_effect_codes,
        max_text=int(t["free_text_max_chars"]),
    )
    if supersedes_id is not None:
        previous = db.get(DiaryEntry, supersedes_id)
        if previous is None or previous.patient_id != patient_id or previous.day != day:
            raise DiaryError("Повторно заполнить можно только свою запись за тот же день")

    entry = DiaryEntry(
        client_id=client_id,
        patient_id=patient_id,
        day=day,
        supersedes_id=supersedes_id,
        filled_late=window is DiaryWindow.LATE,
        client_submitted_at=client_submitted_at,
        submitted_at=now,
        mood=answers.mood,
        interest=answers.interest,
        anxiety=answers.anxiety,
        worry_control=answers.worry_control,
        sleep_hours=answers.sleep_hours,
        sleep_quality=answers.sleep_quality,
        energy=answers.energy,
        meds_taken=answers.meds_taken,
        had_side_effects=answers.had_side_effects,
    )
    db.add(entry)
    db.flush()
    db.add_all(DiarySideEffect(entry_id=entry.id, code=s.code, other_text=s.other_text) for s in answers.side_effects)
    note_patient_activity(db, patient_id, now)
    audit.record(db, actor_account_id=patient.account_id, actor_role="patient", action=AuditAction.CREATE,
                 entity="diary_entry", entity_id=entry.id, patient_id=patient_id)

    raised: list[FlagReason] = []

    def flag(candidate: FlagCandidate | None) -> None:
        if candidate and raise_flag(db, candidate, patient_id=patient_id, source_type="diary_entry",
                                    source_id=entry.id, now=now):
            raised.append(candidate.reason)

    if answers.side_effects:
        raised += record_side_effects(db, patient_id=patient_id, items=answers.side_effects,
                                      source=SideEffectSource.DIARY, source_ref=entry.id, now=now)
    if answers.meds_taken is MedsTaken.SELF_CHANGED:
        flag(flag_rules.self_dose_change("diary", day.isoformat()))

    history = effective_entries(db, patient_id, day - timedelta(days=HISTORY_DAYS - 1), day)
    flag(flag_rules.low_mood({d: e.mood for d, e in history.items()}, day,
                             max_mood=int(t["low_mood_max_yellow"]), days=int(t["low_mood_days_yellow"])))

    has_doctor = active_doctor_id(db, patient_id) is not None
    help_screen = None
    matcher = matcher or default_matcher()
    if any(matcher.is_crisis(text) for text in answers.free_texts()):
        flag(FlagCandidate(FlagLevel.RED, FlagReason.CRISIS_WORDS, f"crisis_words:diary:{entry.id}"))
        help_screen = help_screen_for(content, patient.region_code, has_doctor=has_doctor)

    offer = None
    if has_doctor and not assessed_today(db, patient, now):
        vitals = {d: DayVitals(e.mood, e.anxiety, float(e.sleep_hours) if e.sleep_hours is not None else None)
                  for d, e in history.items()}
        triggers = diary_triggers(vitals, day, t)
        offer = triggers[0] if triggers else None

    db.flush()
    return DiaryResult(entry.id, True, entry.filled_late, raised, help_screen, offer)
