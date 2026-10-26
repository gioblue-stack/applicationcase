"""Пороги (§7.2): значения из content/thresholds.json, переопределяемые строками таблицы threshold.

Так врачи меняют пороги без новой сборки.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import Content
from app.models import Threshold


def get_thresholds(db: Session, content: Content) -> dict[str, int | float]:
    values: dict[str, int | float] = dict(content.thresholds.values)
    for key, value in db.execute(select(Threshold.key, Threshold.value)):
        if key in values:
            values[key] = type(values[key])(value)
    return values
