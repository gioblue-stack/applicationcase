"""Что пациент видит после опросника (§7.3) и пользователь после самопроверки (§3.1).

Пациенту не показываются названия степени тяжести — только мягкие формулировки.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.content.models import PatientTexts
from app.domain.enums import InstrumentCode


class Change(StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    WORSE = "worse"


def classify_change(previous_total: int | None, total: int, *, threshold: int) -> Change | None:
    if previous_total is None:
        return None
    delta = total - previous_total
    if delta >= threshold:
        return Change.WORSE
    if -delta >= threshold:
        return Change.IMPROVED
    return Change.UNCHANGED


def result_text(texts: PatientTexts, instrument: InstrumentCode, total: int) -> str:
    for band in texts.result_bands[instrument]:
        if band.min <= total <= band.max:
            return band.text
    raise ValueError(f"{instrument}: сумма {total} вне шкалы")


@dataclass(frozen=True)
class PatientFeedback:
    result_text: str
    change: Change | None
    change_text: str | None
    note: str  # «Результаты опросников — не диагноз…» — всегда под результатом (§2.1)


def patient_feedback(
    texts: PatientTexts, instrument: InstrumentCode, total: int, previous_total: int | None, *, threshold: int
) -> PatientFeedback:
    change = classify_change(previous_total, total, threshold=threshold)
    return PatientFeedback(
        result_text=result_text(texts, instrument, total),
        change=change,
        change_text=texts.change[change.value] if change else None,
        note=texts.not_diagnosis_note,
    )


class SelfCheckLevel(StrEnum):
    NONE = "none"  # обе суммы 0–4
    MILD = "mild"  # хотя бы одна 5–9
    PRONOUNCED = "pronounced"  # хотя бы одна ≥ 10


def self_check_level(phq9_total: int, gad7_total: int) -> SelfCheckLevel:
    worst = max(phq9_total, gad7_total)
    if worst >= 10:
        return SelfCheckLevel.PRONOUNCED
    if worst >= 5:
        return SelfCheckLevel.MILD
    return SelfCheckLevel.NONE
