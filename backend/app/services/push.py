"""Web Push: напоминания пациенту на телефон (§5.3) и сигналы о флагах врачу в браузер.

На заблокированном экране — только нейтральный текст уведомления (body_neutral): без диагноза, препаратов
и слов «врач», «лечение» (§2.2). Подписка браузера хранится в таблице device (platform = "web").
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

import sqlalchemy as sa
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, object_session

from app.core.config import Settings
from app.domain.enums import NotificationKind
from app.models import Device, Notification
from app.services.notifications import DevLogPushProvider

log = logging.getLogger("mindcare.push")

WEB = "web"
TTL_SECONDS = 6 * 3600  # напоминание, не доставленное за 6 часов, уже не нужно

# Куда открыть сайт по нажатию на уведомление.
OPEN_URL = {
    NotificationKind.DOSE_REMINDER: "/",
    NotificationKind.DIARY_REMINDER: "/diary",
    NotificationKind.WEEKLY_QUESTIONNAIRE: "/",
    NotificationKind.DOCTOR_REPLY: "/messages",
    # Кабинет врача: открывается очередь пациентов, где красные флаги — сверху.
    NotificationKind.RED_FLAG: "/",
    NotificationKind.YELLOW_FLAG: "/",
}


class PushNotConfigured(RuntimeError):
    pass


def configured(settings: Settings) -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key
                and settings.vapid_private_key.get_secret_value())


def _endpoint_of(subscription: dict) -> str:
    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys") or {}
    if not isinstance(endpoint, str) or not endpoint.startswith("https://") or not keys.get("p256dh") \
            or not keys.get("auth"):
        raise ValueError("Некорректная подписка на уведомления")
    return endpoint


def _same_endpoint(endpoint: str):
    return sa.cast(Device.push_token, JSONB)["endpoint"].astext == endpoint


def subscribe(db: Session, *, account_id: uuid.UUID, subscription: dict, now: datetime) -> None:
    """Подписка браузера. Тот же браузер мог быть подписан под другим аккаунтом — переносим на текущий."""
    endpoint = _endpoint_of(subscription)
    db.execute(sa.delete(Device).where(Device.platform == WEB, _same_endpoint(endpoint)))
    db.add(Device(account_id=account_id, platform=WEB, push_token=json.dumps(subscription), last_seen_at=now))
    db.flush()


def unsubscribe(db: Session, *, account_id: uuid.UUID, endpoint: str) -> None:
    db.execute(sa.delete(Device).where(Device.account_id == account_id, Device.platform == WEB,
                                       _same_endpoint(endpoint)))
    db.flush()


def subscriptions_count(db: Session, account_id: uuid.UUID) -> int:
    return len(db.scalars(select(Device.id).where(Device.account_id == account_id, Device.platform == WEB)).all())


class WebPushProvider:
    """Отправляет уведомление на все подписанные браузеры получателя; в лог — как и раньше, нейтрально."""

    def __init__(self, settings: Settings, sender=None):
        if not configured(settings):
            raise PushNotConfigured("Не заданы ключи VAPID")
        self._key = settings.vapid_private_key.get_secret_value()
        self._claims = {"sub": settings.vapid_subject}
        self._sender = sender or webpush  # в тестах подменяется — без запросов к push-сервисам
        self._log = DevLogPushProvider()

    def send(self, notification: Notification) -> None:
        self._log.send(notification)
        self.send_to_account(object_session(notification), notification.recipient_account_id,
                             title=notification.title, body=notification.body_neutral,
                             url=OPEN_URL.get(notification.kind, "/"), tag=notification.kind.value)

    def send_to_account(self, db: Session, account_id: uuid.UUID, *, title: str, body: str, url: str,
                        tag: str) -> int:
        """Возвращает, на сколько устройств ушло. Устаревшие подписки (404/410) удаляются."""
        payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag}, ensure_ascii=False)
        delivered = 0
        for device in db.scalars(select(Device).where(Device.account_id == account_id, Device.platform == WEB)).all():
            try:
                self._sender(subscription_info=json.loads(device.push_token), data=payload,
                             vapid_private_key=self._key, vapid_claims=dict(self._claims), ttl=TTL_SECONDS)
                delivered += 1
            except WebPushException as e:
                status = getattr(e.response, "status_code", None)
                if status in (404, 410):
                    db.delete(device)  # браузер отписался или переустановлен — больше не слать
                    continue
                raise
        db.flush()
        return delivered


def provider_for(settings: Settings):
    """Воркер: настоящий Web Push, если заданы ключи, иначе — только лог."""
    return WebPushProvider(settings) if configured(settings) else DevLogPushProvider()
