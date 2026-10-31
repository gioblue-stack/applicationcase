"""Внешние факторы стресса: короткий опросник при первом входе, ответы видит лечащий врач.

Баллов и порогов нет — это не шкала, а список того, что сейчас давит на человека. Безопасность:
«угрозы или насилие» → жёлтый флаг врачу и совет пациенту; кризисные слова в свободном ответе →
экран помощи сразу и красный флаг, как в сообщениях врачу.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import Content
from app.domain.crisis_words import CrisisMatcher, default_matcher
from app.domain.enums import FlagLevel, FlagReason
from app.domain.flag_rules import FlagCandidate
from app.models import PatientProfile, StressAssessment
from app.services.care import active_doctor_id
from app.services.flags import raise_flag
from app.services.screens import HelpScreen, help_screen_for

OTHER_TEXT_MAX = 500


class StressError(ValueError):
    pass


@dataclass(frozen=True)
class StressResult:
    assessment_id: uuid.UUID
    created: bool
    safety_text: str | None  # отмечены угрозы или насилие
    help_screen: HelpScreen | None  # кризисные слова в свободном ответе


@dataclass(frozen=True)
class StressAnswerView:
    id: str
    group: str
    text: str
    icd: str | None
    value: int | None  # None — не ответил(а)
    label: str


@dataclass(frozen=True)
class StressView:
    assessment_id: uuid.UUID
    submitted_at: datetime
    answers: list[StressAnswerView]  # сначала «влияет сильно», потом «немного», потом остальные
    present_count: int
    strong_count: int
    other_text: str | None


def latest(db: Session, patient_id: uuid.UUID) -> StressAssessment | None:
    return db.scalar(select(StressAssessment).where(StressAssessment.patient_id == patient_id)
                     .order_by(StressAssessment.submitted_at.desc()).limit(1))


def due(db: Session, patient: PatientProfile) -> bool:
    """Предложить на «Сегодня»: пациент подключён к врачу и ещё ни разу не отвечал."""
    return active_doctor_id(db, patient.id) is not None and latest(db, patient.id) is None


def _validate(content: Content, answers: dict[str, int], other_text: str | None) -> str | None:
    instrument = content.stress_factors
    values = {o.value for o in instrument.options}
    for item_id, value in answers.items():
        if instrument.item(item_id) is None:
            raise StressError(f"Неизвестный вопрос: {item_id}")
        if value not in values:
            raise StressError("Ответ — «Нет», «Влияет немного» или «Влияет сильно»")
    text = (other_text or "").strip() or None
    if text and len(text) > OTHER_TEXT_MAX:
        raise StressError(f"Свободный ответ — не длиннее {OTHER_TEXT_MAX} знаков")
    if not answers and not text:
        raise StressError("Ответьте хотя бы на один вопрос")
    return text


def submit(db: Session, *, patient: PatientProfile, client_id: uuid.UUID, answers: dict[str, int],
           other_text: str | None, now: datetime, content: Content,
           matcher: CrisisMatcher | None = None) -> StressResult:
    existing = db.scalar(select(StressAssessment).where(StressAssessment.client_id == client_id))
    if existing is not None:
        if existing.patient_id != patient.id or existing.answers != answers:
            raise StressError("client_id уже использован")
        return StressResult(existing.id, False, None, None)  # повторная отправка — без второго флага

    text = _validate(content, answers, other_text)
    row = StressAssessment(patient_id=patient.id, client_id=client_id, answers=answers, other_text=text,
                           instrument_version=content.stress_factors.version, submitted_at=now)
    db.add(row)
    db.flush()

    has_doctor = active_doctor_id(db, patient.id) is not None
    safety = [i.id for i in content.stress_factors.items if i.safety and answers.get(i.id, 0) > 0]
    if safety and has_doctor:
        raise_flag(db, FlagCandidate(FlagLevel.YELLOW, FlagReason.STRESS_SAFETY, f"stress_safety:{row.id}",
                                     {"items": safety}),
                   patient_id=patient.id, source_type="stress_assessment", source_id=row.id, now=now)

    help_screen = None
    if text and (matcher or default_matcher()).is_crisis(text):
        if has_doctor:
            raise_flag(db, FlagCandidate(FlagLevel.RED, FlagReason.CRISIS_WORDS, f"crisis_words:stress:{row.id}"),
                       patient_id=patient.id, source_type="stress_assessment", source_id=row.id, now=now)
        help_screen = help_screen_for(content, patient.region_code, has_doctor=has_doctor)
    db.flush()
    return StressResult(row.id, True, content.stress_factors.safety_text if safety else None, help_screen)


def view(db: Session, patient_id: uuid.UUID, content: Content) -> StressView | None:
    """Для карточки врача: последнее заполнение, отмеченные факторы — сверху."""
    row = latest(db, patient_id)
    if row is None:
        return None
    instrument = content.stress_factors
    labels = {o.value: o.label for o in instrument.options}
    items = [StressAnswerView(i.id, instrument.groups[i.group], i.text, i.icd, row.answers.get(i.id),
                              labels.get(row.answers.get(i.id), "Нет ответа")) for i in instrument.items]
    items.sort(key=lambda a: -(a.value or 0))
    values = [a.value or 0 for a in items]
    return StressView(row.id, row.submitted_at, items, sum(v > 0 for v in values), sum(v == 2 for v in values),
                      row.other_text)
