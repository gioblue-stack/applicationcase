"""ВРЕМЕННЫЙ демо-вход для презентации: без кода, пароля и TOTP — только за демо-аккаунты из сидов.

Включается переменной MC_DEMO_LOGIN=true и в production не работает. Когда показ закончится:
выключить переменную, а затем удалить этот модуль, маршруты /auth/demo и кнопки «Демо» на страницах входа.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.enums import AuditAction
from app.models import Account, PatientProfile
from app.seed.demo import DEMO_DOCTOR_EMAIL, LOGINS
from app.services import audit
from app.services.auth import AuthError, TokenPair, issue_tokens

# Кого можно выбрать на кнопке «Демо» и что этот персонаж показывает (§7.13).
PATIENTS = {
    "anna": "Стабильное наблюдение",
    "igor": "Пропуски приёма, рост тревоги",
    "maria": "Высокий суицидальный риск",
    "oleg": "Пользователь без врача",
}


class DemoLoginUnavailable(AuthError):
    status = 404

    def __init__(self, message: str = "Демо-вход выключен") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class DemoPatient:
    key: str
    full_name: str
    scenario: str


@dataclass(frozen=True)
class DemoOptions:
    patients: list[DemoPatient]
    doctor: bool


def _check_enabled(settings: Settings) -> None:
    if not settings.demo_login or settings.env == "production":
        raise DemoLoginUnavailable()


def options(db: Session, settings: Settings) -> DemoOptions:
    """Кнопки «Демо» показываются только для аккаунтов, которые реально есть в базе."""
    _check_enabled(settings)
    patients = []
    for key, scenario in PATIENTS.items():
        name = db.scalar(select(PatientProfile.full_name).join(Account, Account.id == PatientProfile.account_id)
                         .where(Account.phone == LOGINS[key]))
        if name:
            patients.append(DemoPatient(key, name, scenario))
    doctor = db.scalar(select(Account.id).where(Account.email == DEMO_DOCTOR_EMAIL)) is not None
    return DemoOptions(patients, doctor)


def login(db: Session, *, who: str, now: datetime, settings: Settings, user_agent: str | None) -> TokenPair:
    _check_enabled(settings)
    if who == "doctor":
        account = db.scalar(select(Account).where(Account.email == DEMO_DOCTOR_EMAIL))
    elif who in PATIENTS:
        account = db.scalar(select(Account).where(Account.phone == LOGINS[who]))
    else:
        raise DemoLoginUnavailable("Нет такого демо-аккаунта")
    if account is None:
        raise DemoLoginUnavailable("Демо-данные не загружены")
    # Вход без кода и TOTP виден в журнале доступа: после презентации такие сессии легко найти.
    audit.record(db, actor_account_id=account.id, actor_role=account.role.value, action=AuditAction.CREATE,
                 entity="demo_session", entity_id=account.id, patient_id=None, meta={"who": who})
    return issue_tokens(db, account, now=now, settings=settings, user_agent=user_agent)
