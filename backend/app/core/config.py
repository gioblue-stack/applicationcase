from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class SecretNotConfigured(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MC_", env_file=".env", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://mindcare@localhost:5432/mindcare"
    content_dir: Path = REPO_ROOT / "content"
    # Вложения пациентов (блок 9) — зашифрованы ключом MC_DATA_KEY; каталог вне репозитория в production.
    upload_dir: Path = REPO_ROOT / "var" / "uploads"
    # Только разработка: коды входа дописываются в этот файл, чтобы не искать их в логе сервера.
    dev_codes_file: Path | None = None

    # Секреты задаются только через окружение; значений по умолчанию нет намеренно.
    jwt_secret: SecretStr | None = None
    data_key: SecretStr | None = None  # base64, 32 байта: шифрование TOTP-секретов врачей
    otp_pepper: SecretStr | None = None  # «перец» для хешей одноразовых кодов входа

    access_ttl_minutes: int = 15
    patient_refresh_ttl_days: int = 30
    # Автоматический выход врача при бездействии (§5.6): refresh-токен живёт столько с последнего обновления.
    doctor_idle_timeout_minutes: int = 30
    mfa_token_ttl_minutes: int = 5

    login_code_ttl_minutes: int = 10
    login_code_max_attempts: int = 5
    login_code_resend_seconds: int = 60

    doctor_max_failed_logins: int = 5
    doctor_lockout_minutes: int = 15

    def secret(self, name: str) -> str:
        value: SecretStr | None = getattr(self, name)
        if value is None or not value.get_secret_value():
            raise SecretNotConfigured(f"Не задан MC_{name.upper()}")
        if name == "jwt_secret" and len(value.get_secret_value()) < 32:
            raise SecretNotConfigured("MC_JWT_SECRET короче 32 символов")
        return value.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
