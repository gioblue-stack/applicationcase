"""Зависимости API: сессия БД, время, настройки, текущий пользователь и доступ врача к пациенту."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.content.loader import load_content
from app.content.models import Content
from app.core import security
from app.core.config import Settings, get_settings
from app.db.session import get_engine
from app.domain.enums import AuditAction, Role
from app.models import Account, PatientProfile
from app.services import audit
from app.services.code_sender import CodeSender, default_sender
from app.services.patients import doctor_has_patient


def get_db() -> Iterator[Session]:
    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_now() -> datetime:
    return security.utcnow()


def get_app_settings() -> Settings:
    return get_settings()


def get_content() -> Content:
    return load_content()


def get_code_sender(settings: Annotated[Settings, Depends(get_app_settings)]) -> CodeSender:
    return default_sender(settings)


DB = Annotated[Session, Depends(get_db)]
Now = Annotated[datetime, Depends(get_now)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
ContentDep = Annotated[Content, Depends(get_content)]

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    account_id: uuid.UUID
    role: Role


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def current_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)], db: DB, now: Now, settings: AppSettings,
) -> Principal:
    if creds is None:
        raise _unauthorized("Нужен вход")
    try:
        claims = security.decode_jwt(settings.secret("jwt_secret"), creds.credentials, purpose=security.ACCESS, now=now)
    except security.InvalidToken as e:
        raise _unauthorized(str(e)) from e
    account = db.get(Account, claims.account_id)
    if account is None or not account.is_active:
        raise _unauthorized("Учётная запись недоступна")
    return Principal(account.id, account.role)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def current_patient(principal: CurrentPrincipal, db: DB) -> PatientProfile:
    if principal.role not in (Role.PATIENT, Role.SELF_USER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступно только в приложении пациента")
    patient = db.scalar(select(PatientProfile).where(PatientProfile.account_id == principal.account_id))
    if patient is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Профиль не найден")
    return patient


def current_doctor(principal: CurrentPrincipal) -> Principal:
    if principal.role is not Role.DOCTOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступно только врачу")
    return principal


CurrentPatient = Annotated[PatientProfile, Depends(current_patient)]
CurrentDoctor = Annotated[Principal, Depends(current_doctor)]


def require_doctor_access(db: Session, doctor: Principal, patient_id: uuid.UUID, request: Request) -> PatientProfile:
    """Данные пациента видит только его лечащий врач; каждый просмотр — в журнал доступа (§5.6).

    Чужой пациент неотличим от несуществующего: 404, а не 403.
    """
    if not doctor_has_patient(db, doctor.account_id, patient_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пациент не найден")
    audit.record(db, actor_account_id=doctor.account_id, actor_role="doctor", action=AuditAction.VIEW,
                 entity="patient", entity_id=patient_id, patient_id=patient_id,
                 ip=request.client.host if request.client else None,
                 meta={"method": request.method, "path": request.url.path})
    return db.get(PatientProfile, patient_id)


def doctor_patient(patient_id: uuid.UUID, request: Request, doctor: CurrentDoctor, db: DB) -> PatientProfile:
    return require_doctor_access(db, doctor, patient_id, request)


DoctorPatient = Annotated[PatientProfile, Depends(doctor_patient)]
