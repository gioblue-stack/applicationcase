"""Подсчёт PHQ-9 и GAD-7 (§4.4, §4.5).

Хранится ответ на каждый вопрос; сумма — производная. Вопрос PHQ-9 о трудностях в сумму не входит.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.content.models import InstrumentDef


class InvalidQuestionnaire(ValueError):
    pass


def validate_answers(instrument: InstrumentDef, answers: Sequence[int]) -> None:
    if len(answers) != len(instrument.items):
        raise InvalidQuestionnaire(
            f"{instrument.code}: ожидается {len(instrument.items)} ответов, получено {len(answers)}"
        )
    allowed = {option.value for option in instrument.options}
    for no, value in enumerate(answers, start=1):
        if isinstance(value, bool) or value not in allowed:
            raise InvalidQuestionnaire(f"{instrument.code}: недопустимый ответ на вопрос {no}: {value!r}")


def total_score(instrument: InstrumentDef, answers: Sequence[int]) -> int:
    validate_answers(instrument, answers)
    return sum(answers)


def severity_band_for_doctor(instrument: InstrumentDef, total: int) -> str:
    """Название степени выраженности. Только для врача: пациент видит мягкие формулировки (§7.3)."""
    for band in instrument.severity_bands_doctor_only:
        if band.min <= total <= band.max:
            return band.label
    raise InvalidQuestionnaire(f"{instrument.code}: сумма {total} вне диапазона")


def safety_item_value(instrument: InstrumentDef, answers: Sequence[int]) -> int | None:
    """Ответ на вопрос о мыслях о смерти (PHQ-9, п. 9). None для опросников без такого вопроса."""
    if instrument.safety_item is None:
        return None
    validate_answers(instrument, answers)
    return answers[instrument.safety_item - 1]
