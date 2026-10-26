"""Доставка одноразовых кодов входа (SMS / e-mail).

Настоящий провайдер подключается к пилоту. В разработке код пишется в лог сервера;
в production без провайдера сервис не стартует, а не шлёт коды в лог.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.core.config import Settings

log = logging.getLogger("mindcare.login_codes")


class CodeSender(Protocol):
    def send(self, login: str, code: str) -> None: ...


class DevLogSender:
    def send(self, login: str, code: str) -> None:
        log.warning("DEV: код входа для %s — %s", login, code)


class SenderNotConfigured(RuntimeError):
    pass


def default_sender(settings: Settings) -> CodeSender:
    if settings.env in ("development", "test"):
        return DevLogSender()
    raise SenderNotConfigured("В production нужен провайдер SMS/e-mail для кодов входа")
