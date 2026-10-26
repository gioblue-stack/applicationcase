from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domain.enums import AuditAction
from app.models import AuditLog


def record(
    db: Session,
    *,
    actor_account_id: uuid.UUID | None,
    actor_role: str,
    action: AuditAction,
    entity: str,
    entity_id: object | None,
    patient_id: uuid.UUID | None,
    meta: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_account_id=actor_account_id,
            actor_role=actor_role,
            action=action,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id),
            patient_id=patient_id,
            ip=ip,
            meta=meta,
        )
    )
