"""План безопасности (§2.5). MVP: пациент заполняет поля, врач просматривает.

Каждое сохранение — новая версия; прежние остаются. План открывается на экране помощи без интернета,
поэтому приложение кэширует его на устройстве.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import AuditAction
from app.models import Account, PatientProfile, SafetyPlan
from app.services import audit


class SafetyPlanError(ValueError):
    pass


@dataclass(frozen=True)
class Contact:
    name: str
    phone: str | None = None


@dataclass(frozen=True)
class SafetyPlanInput:
    warning_signs: str | None = None
    coping_strategies: str | None = None
    contacts: list[Contact] = field(default_factory=list)
    professionals: list[Contact] = field(default_factory=list)
    means_restriction: str | None = None

    def is_empty(self) -> bool:
        texts = (self.warning_signs, self.coping_strategies, self.means_restriction)
        return not any(t and t.strip() for t in texts) and not self.contacts and not self.professionals


@dataclass(frozen=True)
class SafetyPlanView:
    version: int
    versions_total: int
    warning_signs: str | None
    coping_strategies: str | None
    contacts: list[dict]
    professionals: list[dict]
    means_restriction: str | None
    updated_at: datetime
    updated_by_role: str
    doctor_reviewed_at: datetime | None


def _latest(db: Session, patient_id: uuid.UUID) -> SafetyPlan | None:
    return db.scalar(select(SafetyPlan).where(SafetyPlan.patient_id == patient_id)
                     .order_by(SafetyPlan.version.desc()).limit(1))


def current_plan(db: Session, patient_id: uuid.UUID) -> SafetyPlanView | None:
    plan = _latest(db, patient_id)
    if plan is None:
        return None
    total = db.scalar(select(func.count()).select_from(SafetyPlan).where(SafetyPlan.patient_id == patient_id))
    author = db.get(Account, plan.updated_by)
    return SafetyPlanView(
        version=plan.version, versions_total=total, warning_signs=plan.warning_signs,
        coping_strategies=plan.coping_strategies, contacts=plan.contacts or [], professionals=plan.professionals or [],
        means_restriction=plan.means_restriction, updated_at=plan.created_at,
        updated_by_role=author.role.value if author else "unknown", doctor_reviewed_at=plan.doctor_reviewed_at,
    )


def save_by_patient(db: Session, *, patient: PatientProfile, data: SafetyPlanInput, now: datetime) -> SafetyPlanView:
    if data.is_empty():
        raise SafetyPlanError("Заполните хотя бы один раздел плана")
    latest = _latest(db, patient.id)
    plan = SafetyPlan(
        patient_id=patient.id, version=(latest.version + 1) if latest else 1, updated_by=patient.account_id,
        created_at=now, warning_signs=data.warning_signs, coping_strategies=data.coping_strategies,
        contacts=[c.__dict__ for c in data.contacts], professionals=[c.__dict__ for c in data.professionals],
        means_restriction=data.means_restriction,
    )
    db.add(plan)
    audit.record(db, actor_account_id=patient.account_id, actor_role="patient", action=AuditAction.CREATE,
                 entity="safety_plan", entity_id=patient.id, patient_id=patient.id, meta={"version": plan.version})
    db.flush()
    return current_plan(db, patient.id)


def mark_reviewed(db: Session, *, doctor_account_id: uuid.UUID, patient_id: uuid.UUID, now: datetime) -> SafetyPlanView:
    """Врач просмотрел актуальную версию — отметка видна и пациенту."""
    plan = _latest(db, patient_id)
    if plan is None:
        raise SafetyPlanError("План безопасности ещё не заполнен")
    plan.doctor_reviewed_at = now
    audit.record(db, actor_account_id=doctor_account_id, actor_role="doctor", action=AuditAction.UPDATE,
                 entity="safety_plan", entity_id=patient_id, patient_id=patient_id,
                 meta={"version": plan.version, "reviewed": True})
    db.flush()
    return current_plan(db, patient_id)
