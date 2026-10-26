"""Журнал побочных эффектов и тревожные симптомы (§1.1, §5.4 блок 2, §7.5)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import RISK_PROTOCOL_ACTION, Content
from app.domain import flag_rules
from app.domain.diary import SideEffectAnswer
from app.domain.enums import FlagReason, SideEffectSource
from app.domain.flag_rules import FlagCandidate
from app.models import SideEffectReport
from app.services.flags import raise_flag


def known_side_effect_keys(db: Session, patient_id: uuid.UUID) -> set[str]:
    rows = db.execute(
        select(SideEffectReport.code, SideEffectReport.other_text).where(SideEffectReport.patient_id == patient_id)
    )
    return {flag_rules.side_effect_key(code, text) for code, text in rows}


def record_side_effects(
    db: Session,
    *,
    patient_id: uuid.UUID,
    items: Sequence[SideEffectAnswer],
    source: SideEffectSource,
    source_ref: uuid.UUID | None,
    now: datetime,
) -> list[FlagReason]:
    """Записывает эффекты в журнал. Новый для пациента эффект — жёлтый флаг врачу."""
    known = known_side_effect_keys(db, patient_id)
    raised: list[FlagReason] = []
    for item in items:
        candidate = flag_rules.new_side_effect(item.code, item.other_text, known_keys=known)
        report = SideEffectReport(
            patient_id=patient_id, code=item.code, other_text=item.other_text, source=source,
            source_ref=source_ref, is_new=candidate is not None, reported_at=now,
        )
        db.add(report)
        db.flush()
        known.add(flag_rules.side_effect_key(item.code, item.other_text))
        if candidate and raise_flag(db, candidate, patient_id=patient_id, source_type="side_effect_report",
                                    source_id=report.id, now=now):
            raised.append(candidate.reason)
    return raised


@dataclass(frozen=True)
class AlarmingSymptomResult:
    action: str
    patient_text: str | None  # что делать: 112 / связаться с врачом сегодня
    flag_id: uuid.UUID | None
    start_risk_protocol: bool  # «Мысли о самоубийстве появились или усилились» → уточняющий блок


def report_alarming_symptom(
    db: Session, *, patient_id: uuid.UUID, code: str, now: datetime, content: Content
) -> AlarmingSymptomResult:
    symptom = content.alarming_symptoms.by_code(code)
    known = known_side_effect_keys(db, patient_id)
    report = SideEffectReport(
        patient_id=patient_id, code=code, source=SideEffectSource.ASSISTANT, alarming_symptom_code=code,
        is_new=code not in known, reported_at=now,
    )
    db.add(report)
    db.flush()

    if symptom.action == RISK_PROTOCOL_ACTION:
        # Уровень определит уточняющий блок; флаг поставит протокол безопасности.
        return AlarmingSymptomResult(symptom.action, None, None, start_risk_protocol=True)

    assert symptom.flag_level is not None
    flag = raise_flag(
        db,
        FlagCandidate(symptom.flag_level, FlagReason.ALARMING_SYMPTOM, f"alarming_symptom:{report.id}", {"code": code}),
        patient_id=patient_id,
        source_type="side_effect_report",
        source_id=report.id,
        now=now,
    )
    return AlarmingSymptomResult(
        symptom.action, content.alarming_symptoms.action_texts[symptom.action],
        flag.id if flag else None, start_risk_protocol=False,
    )
