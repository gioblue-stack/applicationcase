"""Доставка одноразовых кодов входа (SMS / e-mail).

Настоящий провайдер подключается к пилоту. В разработке код пишется в лог сервера;
в production без провайдера сервис не стартует, а не шлёт коды в лог.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.core.config import Settings

log = logging.getLogger("mindcare.login_codes")


class CodeSender(Protocol):
    def send(self, login: str, code: str) -> None: ...


class DevLogSender:
    def __init__(self, codes_file: Path | None = None):
        self.codes_file = codes_file

    def send(self, login: str, code: str) -> None:
        log.warning("DEV: код входа для %s — %s", login, code)
        if self.codes_file is not None:
            # Свежий код — последней строкой; файл лежит в var/ и в git не попадает.
            with self.codes_file.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%H:%M:%S}  {login}  →  {code}\n")


class SenderNotConfigured(RuntimeError):
    pass


def default_sender(settings: Settings) -> CodeSender:
    if settings.env in ("development", "test"):
        return DevLogSender(settings.dev_codes_file if settings.env == "development" else None)
    raise SenderNotConfigured("В production нужен провайдер SMS/e-mail для кодов входа")
