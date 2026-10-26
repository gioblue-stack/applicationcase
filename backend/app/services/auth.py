"""Вход и регистрация (§5.2).

Пациент и пользователь — телефон или e-mail + одноразовый код. Врач — пароль + TOTP (обязательно).
Ответы об ошибках одинаковы для «нет такого аккаунта» и «неверный код/пароль»: по ним нельзя
узнать, зарегистрирован ли человек.
"""

from __future__ import annotations

import hmac
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.content.models import Content
from app.core import security
from app.core.config import Settings
from app.domain.enums import AuditAction, CareLinkStatus, ConsentKind, Role
from app.models import Account, CareLink, Consent, DoctorProfile, LoginCode, PatientProfile, RefreshToken
from app.services import audit
from app.services.code_sender import CodeSender
from app.services.patients import is_adult

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    status = 401


class InvalidCredentials(AuthError):
    def __init__(self, message: str = "Неверный код или пароль") -> None:
        super().__init__(message)


class TooManyRequests(AuthError):
    status = 429

    def __init__(self, retry_after: int) -> None:
        super().__init__("Слишком часто. Попробуйте позже")
        self.retry_after = retry_after


class AccountLocked(AuthError):
    status = 423

    def __init__(self, until: datetime) -> None:
        super().__init__("Вход временно заблокирован после нескольких неудачных попыток")
        self.until = until


class RegistrationError(AuthError):
    status = 422


class LoginTaken(AuthError):
    status = 409

    def __init__(self) -> None:
        super().__init__("Этот телефон или e-mail уже зарегистрирован — войдите по коду")


class TotpAlreadyConfigured(AuthError):
    status = 409

    def __init__(self) -> None:
        super().__init__("Двухфакторный вход уже настроен; сброс — через администратора")


def normalize_login(raw: str) -> str:
    value = raw.strip().lower()
    if "@" in value:
        if not _EMAIL.match(value):
            raise RegistrationError("Неверный e-mail")
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if not 11 <= len(digits) <= 15:
        raise RegistrationError("Неверный номер телефона")
    return "+" + digits


def _login_columns(login: str) -> dict:
    return {"email": login} if "@" in login else {"phone": login}


def _account_by_login(db: Session, login: str) -> Account | None:
    return db.scalar(select(Account).where(or_(Account.phone == login, Account.email == login)))


# --- Одноразовые коды ------------------------------------------------------------------------


def request_login_code(db: Session, *, login: str, now: datetime, settings: Settings, sender: CodeSender) -> None:
    """Код отправляется на любой корректный телефон/e-mail — и для входа, и для регистрации."""
    login = normalize_login(login)
    last = db.scalar(select(LoginCode.created_at).where(LoginCode.login == login)
                     .order_by(LoginCode.created_at.desc()).limit(1))
    wait = timedelta(seconds=settings.login_code_resend_seconds)
    if last is not None and now - last < wait:
        raise TooManyRequests(int((last + wait - now).total_seconds()) + 1)
    code = security.new_login_code()
    db.add(LoginCode(login=login, code_hash=security.hash_secret(settings.secret("otp_pepper"), f"{login}:{code}"),
                     expires_at=now + timedelta(minutes=settings.login_code_ttl_minutes), created_at=now))
    db.flush()
    sender.send(login, code)


def _consume_code(db: Session, login: str, code: str, now: datetime, settings: Settings) -> None:
    row = db.scalar(
        select(LoginCode)
        .where(LoginCode.login == login, LoginCode.consumed_at.is_(None), LoginCode.expires_at > now)
        .order_by(LoginCode.created_at.desc())
        .limit(1)
    )
    if row is None or row.attempts >= settings.login_code_max_attempts:
        raise InvalidCredentials()
    expected = security.hash_secret(settings.secret("otp_pepper"), f"{login}:{code.strip()}")
    if not hmac.compare_digest(expected, row.code_hash):
        row.attempts += 1  # вызывающий код фиксирует попытку даже при ошибке
        db.flush()
        raise InvalidCredentials()
    row.consumed_at = now


# --- Токены ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    role: Role
    token_type: str = "bearer"


def _refresh_ttl(role: Role, settings: Settings) -> timedelta:
    if role is Role.DOCTOR:
        return timedelta(minutes=settings.doctor_idle_timeout_minutes)
    return timedelta(days=settings.patient_refresh_ttl_days)


def issue_tokens(db: Session, account: Account, *, now: datetime, settings: Settings,
                 family_id: uuid.UUID | None = None, user_agent: str | None = None) -> TokenPair:
    access_ttl = timedelta(minutes=settings.access_ttl_minutes)
    access = security.encode_jwt(settings.secret("jwt_secret"), account_id=account.id, role=account.role.value,
                                 purpose=security.ACCESS, now=now, ttl=access_ttl)
    raw = security.new_refresh_token()
    refresh_expires = now + _refresh_ttl(account.role, settings)
    db.add(RefreshToken(account_id=account.id, family_id=family_id or uuid.uuid4(),
                        token_hash=security.hash_secret(settings.secret("otp_pepper"), raw),
                        expires_at=refresh_expires, user_agent=user_agent, created_at=now))
    db.flush()
    return TokenPair(access, raw, now + access_ttl, refresh_expires, account.role)


def refresh_tokens(db: Session, *, refresh_token: str, now: datetime, settings: Settings) -> TokenPair:
    row = db.scalar(select(RefreshToken).where(
        RefreshToken.token_hash == security.hash_secret(settings.secret("otp_pepper"), refresh_token)))
    if row is None:
        raise InvalidCredentials("Сессия недействительна — войдите заново")
    if row.revoked_at is not None:
        # Повтор уже использованного токена: возможна кража — закрываем всю цепочку сессии.
        _revoke_family(db, row.family_id, now)
        raise InvalidCredentials("Сессия недействительна — войдите заново")
    account = db.get(Account, row.account_id)
    if row.expires_at <= now or account is None or not account.is_active:
        raise InvalidCredentials("Сессия истекла — войдите заново")
    row.revoked_at = now
    return issue_tokens(db, account, now=now, settings=settings, family_id=row.family_id, user_agent=row.user_agent)


def _revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=now))
    db.flush()


def logout(db: Session, *, refresh_token: str, now: datetime, settings: Settings) -> None:
    row = db.scalar(select(RefreshToken).where(
        RefreshToken.token_hash == security.hash_secret(settings.secret("otp_pepper"), refresh_token)))
    if row is not None:
        _revoke_family(db, row.family_id, now)


# --- Пациент и пользователь ------------------------------------------------------------------


def login_with_code(db: Session, *, login: str, code: str, now: datetime, settings: Settings) -> TokenPair:
    login = normalize_login(login)
    _consume_code(db, login, code, now, settings)
    account = _account_by_login(db, login)
    if account is None or account.role is Role.DOCTOR or not account.is_active:
        raise InvalidCredentials()
    return issue_tokens(db, account, now=now, settings=settings)


def _check_consent(accepted: bool, version: str, content: Content) -> None:
    if not accepted:
        raise RegistrationError("Без согласия на обработку данных о здоровье регистрация невозможна")
    if version != content.consent.version:
        raise RegistrationError("Текст согласия обновился — прочитайте актуальную версию")


def _new_account(db: Session, *, role: Role, login: str, consent_version: str, now: datetime) -> Account:
    if _account_by_login(db, login) is not None:
        raise LoginTaken()
    account = Account(role=role, created_at=now, **_login_columns(login))
    db.add(account)
    db.flush()
    db.add(Consent(account_id=account.id, kind=ConsentKind.HEALTH_DATA, text_version=consent_version,
                   method="электронное согласие в приложении", given_at=now))
    return account


def register_patient(db: Session, *, invite_code: str, login: str, code: str, consent_accepted: bool,
                     consent_version: str, now: datetime, settings: Settings, content: Content) -> TokenPair:
    """Привязка к врачу по коду-приглашению или QR (§5.2)."""
    _check_consent(consent_accepted, consent_version, content)
    login = normalize_login(login)
    link = db.scalar(select(CareLink).where(CareLink.invite_code == invite_code.strip().upper()))
    if link is None or link.status is not CareLinkStatus.PENDING or link.invite_expires_at <= now:
        raise RegistrationError("Код приглашения недействителен или устарел — попросите врача выдать новый")
    _consume_code(db, login, code, now, settings)
    patient = db.get(PatientProfile, link.patient_id)
    if patient.account_id is not None:
        raise RegistrationError("Карточка уже подключена")
    account = _new_account(db, role=Role.PATIENT, login=login, consent_version=consent_version, now=now)
    patient.account_id = account.id
    link.status, link.linked_at = CareLinkStatus.ACTIVE, now
    audit.record(db, actor_account_id=account.id, actor_role="patient", action=AuditAction.CREATE,
                 entity="care_link", entity_id=link.id, patient_id=patient.id)
    return issue_tokens(db, account, now=now, settings=settings)


def register_self_user(db: Session, *, login: str, code: str, full_name: str, birth_date: date,
                       region_code: str | None, consent_accepted: bool, consent_version: str, now: datetime,
                       settings: Settings, content: Content) -> TokenPair:
    """Пользователь без врача: самопроверка и каталог (§3)."""
    _check_consent(consent_accepted, consent_version, content)
    if not is_adult(birth_date, now.date()):
        raise RegistrationError("Приложение рассчитано на взрослых (18+)")
    login = normalize_login(login)
    _consume_code(db, login, code, now, settings)
    account = _new_account(db, role=Role.SELF_USER, login=login, consent_version=consent_version, now=now)
    db.add(PatientProfile(account_id=account.id, full_name=full_name.strip(), birth_date=birth_date,
                          region_code=region_code, created_at=now))
    return issue_tokens(db, account, now=now, settings=settings)


# --- Врач: пароль + TOTP ---------------------------------------------------------------------


def create_doctor(db: Session, *, email: str, password: str, full_name: str, specialty: str) -> DoctorProfile:
    if len(password) < security.MIN_PASSWORD_LENGTH:
        raise RegistrationError(f"Пароль не короче {security.MIN_PASSWORD_LENGTH} символов")
    login = normalize_login(email)
    if "@" not in login:
        raise RegistrationError("Врач входит по e-mail")
    if _account_by_login(db, login) is not None:
        raise LoginTaken()
    account = Account(role=Role.DOCTOR, email=login, password_hash=security.hash_password(password))
    db.add(account)
    db.flush()
    doctor = DoctorProfile(account_id=account.id, full_name=full_name, specialty=specialty)
    db.add(doctor)
    db.flush()
    return doctor


@dataclass(frozen=True)
class MfaChallenge:
    mfa_token: str
    totp_enrolled: bool


@dataclass(frozen=True)
class TotpSetup:
    secret: str
    otpauth_uri: str


def _check_not_locked(account: Account, now: datetime) -> None:
    if account.locked_until is not None and account.locked_until > now:
        raise AccountLocked(account.locked_until)


def _register_failure(db: Session, account: Account, now: datetime, settings: Settings) -> None:
    account.failed_login_count += 1
    if account.failed_login_count >= settings.doctor_max_failed_logins:
        account.locked_until = now + timedelta(minutes=settings.doctor_lockout_minutes)
        account.failed_login_count = 0
    db.flush()


def doctor_password_login(db: Session, *, email: str, password: str, now: datetime, settings: Settings) -> MfaChallenge:
    """Первый фактор. Токен доступа выдаётся только после второго (TOTP)."""
    try:
        login = normalize_login(email)
    except RegistrationError:
        raise InvalidCredentials() from None
    account = _account_by_login(db, login)
    if account is not None and account.role is Role.DOCTOR:
        _check_not_locked(account, now)
    if account is None or account.role is not Role.DOCTOR or not account.is_active \
            or not security.verify_password(password, account.password_hash):
        if account is not None and account.role is Role.DOCTOR:
            _register_failure(db, account, now, settings)
        raise InvalidCredentials()
    token = security.encode_jwt(settings.secret("jwt_secret"), account_id=account.id, role=Role.DOCTOR.value,
                                purpose=security.MFA, now=now, ttl=timedelta(minutes=settings.mfa_token_ttl_minutes))
    return MfaChallenge(token, account.totp_confirmed_at is not None)


def _mfa_account(db: Session, mfa_token: str, now: datetime, settings: Settings) -> Account:
    try:
        claims = security.decode_jwt(settings.secret("jwt_secret"), mfa_token, purpose=security.MFA, now=now)
    except security.InvalidToken as e:
        raise InvalidCredentials("Начните вход заново") from e
    account = db.get(Account, claims.account_id)
    if account is None or account.role is not Role.DOCTOR or not account.is_active:
        raise InvalidCredentials("Начните вход заново")
    _check_not_locked(account, now)
    return account


def setup_totp(db: Session, *, mfa_token: str, now: datetime, settings: Settings) -> TotpSetup:
    """Первичная настройка приложения-аутентификатора. Подтверждается первым верным кодом."""
    account = _mfa_account(db, mfa_token, now, settings)
    if account.totp_confirmed_at is not None:
        raise TotpAlreadyConfigured()
    secret = security.new_totp_secret()
    account.totp_secret_enc = security.encrypt(settings.secret("data_key"), secret)
    db.flush()
    return TotpSetup(secret, security.totp_uri(secret, account.email or str(account.id)))


def complete_doctor_mfa(db: Session, *, mfa_token: str, code: str, now: datetime, settings: Settings,
                        user_agent: str | None = None) -> TokenPair:
    account = _mfa_account(db, mfa_token, now, settings)
    if account.totp_secret_enc is None:
        raise InvalidCredentials("Сначала настройте двухфакторный вход")
    secret = security.decrypt(settings.secret("data_key"), account.totp_secret_enc)
    step = security.verify_totp(secret, code.strip(), now, last_used_step=account.totp_last_step)
    if step is None:
        _register_failure(db, account, now, settings)
        raise InvalidCredentials()
    account.totp_last_step = step
    account.totp_confirmed_at = account.totp_confirmed_at or now
    account.failed_login_count, account.locked_until = 0, None
    audit.record(db, actor_account_id=account.id, actor_role="doctor", action=AuditAction.CREATE,
                 entity="session", entity_id=None, patient_id=None)
    return issue_tokens(db, account, now=now, settings=settings, user_agent=user_agent)
