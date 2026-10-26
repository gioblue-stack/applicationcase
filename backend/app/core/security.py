"""Криптографические примитивы: пароли, TOTP (RFC 6238), шифрование, токены."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- Пароли (scrypt из стандартной библиотеки) -----------------------------------------------

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        # Сравнение всё равно выполняется, чтобы время ответа не выдавало отсутствие учётной записи.
        hashlib.scrypt(password.encode(), salt=b"0" * 16, **_SCRYPT)
        return False
    _, salt, digest = stored.split("$")
    candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), **_SCRYPT)
    return hmac.compare_digest(candidate, base64.b64decode(digest))


# --- TOTP (RFC 6238: SHA-1, 30 секунд, 6 цифр) -----------------------------------------------

TOTP_STEP = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1  # допускаем расхождение часов на ±1 шаг


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _b32(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def totp_at(secret_bytes: bytes, step: int, digits: int = TOTP_DIGITS) -> str:
    mac = hmac.new(secret_bytes, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % 10**digits).zfill(digits)


def totp_step(now: datetime) -> int:
    return int(now.timestamp()) // TOTP_STEP


def totp_code(secret: str, now: datetime) -> str:
    """Текущий код — то, что показывает приложение-аутентификатор врача."""
    return totp_at(_b32(secret), totp_step(now))


def verify_totp(secret: str, code: str, now: datetime, *, last_used_step: int | None) -> int | None:
    """Возвращает шаг, на котором код совпал, или None. Уже использованный шаг не принимается (защита от повтора)."""
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return None
    current = totp_step(now)
    for step in range(current - TOTP_WINDOW, current + TOTP_WINDOW + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(totp_at(_b32(secret), step), code):
            return step
    return None


def totp_uri(secret: str, account: str, issuer: str = "MindCare demo") -> str:
    from urllib.parse import quote

    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


# --- Шифрование секретов (AES-256-GCM) -------------------------------------------------------


def _key(data_key: str) -> bytes:
    key = base64.b64decode(data_key)
    if len(key) != 32:
        raise ValueError("MC_DATA_KEY должен быть base64 от 32 байт")
    return key


def encrypt_bytes(data_key: str, data: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(_key(data_key)).encrypt(nonce, data, None)


def decrypt_bytes(data_key: str, blob: bytes) -> bytes:
    return AESGCM(_key(data_key)).decrypt(blob[:12], blob[12:], None)


def encrypt(data_key: str, plaintext: str) -> bytes:
    return encrypt_bytes(data_key, plaintext.encode())


def decrypt(data_key: str, blob: bytes) -> str:
    return decrypt_bytes(data_key, blob).decode()


# --- Одноразовые коды и непрозрачные токены --------------------------------------------------


def new_login_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_secret(pepper: str, value: str) -> str:
    """HMAC с «перцем»: утечка таблицы кодов/токенов не даёт подобрать их офлайн."""
    return hmac.new(pepper.encode(), value.encode(), hashlib.sha256).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без 0/O и 1/I — код вводят руками


def new_invite_code(length: int = 8) -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(length))


# --- JWT -------------------------------------------------------------------------------------

ACCESS = "access"
MFA = "mfa"


class InvalidToken(Exception):
    pass


@dataclass(frozen=True)
class TokenClaims:
    account_id: uuid.UUID
    role: str
    purpose: str


def encode_jwt(secret: str, *, account_id: uuid.UUID, role: str, purpose: str, now: datetime, ttl: timedelta) -> str:
    payload = {"sub": str(account_id), "role": role, "pur": purpose, "iat": int(now.timestamp()),
               "exp": int((now + ttl).timestamp()), "jti": secrets.token_hex(8)}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(secret: str, token: str, *, purpose: str, now: datetime) -> TokenClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False})
    except jwt.PyJWTError as e:
        raise InvalidToken("Недействительный токен") from e
    if payload.get("pur") != purpose:
        raise InvalidToken("Токен не для этой операции")
    if payload.get("exp", 0) <= int(now.timestamp()):
        raise InvalidToken("Срок действия токена истёк")
    return TokenClaims(uuid.UUID(payload["sub"]), payload["role"], payload["pur"])


def utcnow() -> datetime:
    return datetime.now(UTC)
