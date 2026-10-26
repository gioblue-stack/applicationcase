import base64
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.exceptions import InvalidTag

from app.core import security

RFC_SECRET = b"12345678901234567890"
K1, K2 = "k1" * 16, "k2" * 16  # ключи HMAC не короче 32 байт


@pytest.mark.parametrize(
    ("unix_time", "expected"),
    [(59, "94287082"), (1111111109, "07081804"), (1234567890, "89005924"), (2000000000, "69279037")],
)
def test_totp_matches_rfc6238_vectors(unix_time, expected):
    assert security.totp_at(RFC_SECRET, unix_time // 30, digits=8) == expected


NOW = datetime(2026, 10, 26, 12, 0, 10, tzinfo=UTC)


def test_totp_accepts_one_step_of_clock_drift_only():
    secret = security.new_totp_secret()
    for drift, ok in ((0, True), (-30, True), (30, True), (-60, False), (60, False)):
        code = security.totp_code(secret, NOW + timedelta(seconds=drift))
        assert (security.verify_totp(secret, code, NOW, last_used_step=None) is not None) is ok


def test_totp_code_cannot_be_reused():
    secret = security.new_totp_secret()
    code = security.totp_code(secret, NOW)
    step = security.verify_totp(secret, code, NOW, last_used_step=None)
    assert security.verify_totp(secret, code, NOW, last_used_step=step) is None


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef"])
def test_totp_rejects_malformed_codes(code):
    assert security.verify_totp(security.new_totp_secret(), code, NOW, last_used_step=None) is None


def test_password_hashing():
    stored = security.hash_password("correct horse battery")
    assert security.verify_password("correct horse battery", stored)
    assert not security.verify_password("correct horse batterY", stored)
    assert security.hash_password("correct horse battery") != stored  # своя соль
    assert not security.verify_password("anything", None)


def test_encryption_roundtrip_and_tamper_detection():
    key = base64.b64encode(secrets.token_bytes(32)).decode()
    blob = security.encrypt(key, "JBSWY3DPEHPK3PXP")
    assert security.decrypt(key, blob) == "JBSWY3DPEHPK3PXP"
    with pytest.raises(InvalidTag):
        security.decrypt(key, blob[:-1] + bytes([blob[-1] ^ 1]))
    with pytest.raises(ValueError, match="32 байт"):
        security.encrypt(base64.b64encode(b"short").decode(), "x")


def test_jwt_checks_purpose_expiry_and_signature():
    account = uuid.uuid4()
    token = security.encode_jwt(K1, account_id=account, role="doctor", purpose=security.MFA, now=NOW,
                                ttl=timedelta(minutes=5))
    assert security.decode_jwt(K1, token, purpose=security.MFA, now=NOW).account_id == account
    with pytest.raises(security.InvalidToken, match="не для этой операции"):
        security.decode_jwt(K1, token, purpose=security.ACCESS, now=NOW)
    with pytest.raises(security.InvalidToken, match="истёк"):
        security.decode_jwt(K1, token, purpose=security.MFA, now=NOW + timedelta(minutes=5))
    with pytest.raises(security.InvalidToken, match="Недействительный"):
        security.decode_jwt(K2, token, purpose=security.MFA, now=NOW)


def test_secret_hash_depends_on_pepper():
    assert security.hash_secret("p1", "x") == security.hash_secret("p1", "x")
    assert security.hash_secret("p1", "x") != security.hash_secret("p2", "x")


def test_invite_codes_avoid_ambiguous_characters():
    code = security.new_invite_code()
    assert len(code) == 8 and not set(code) & set("01IO")
