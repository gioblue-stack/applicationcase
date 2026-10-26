"""Протокол при суицидальном риске (Положение §4.6, тексты §7.1, решения В1–В3).

Чистые функции без БД и I/O. Результат — уровень реагирования, а не балл:
приложение не оценивает и не предсказывает риск, а не даёт пропустить сигнал.
Машинного обучения здесь нет и быть не должно (§4.6).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import StrEnum

from app.domain.enums import AssessmentOutcome, FlagLevel, FlagReason, PushPriority, ResponseLevel

QUESTION_IDS = ("q1", "q2", "q3", "q4", "q5", "q6")
# Способ, намерение и план спрашиваются, только если есть активные мысли (q2 = «да»).
FOLLOW_UP_IDS = ("q3", "q4", "q5")

_LEVEL_ORDER = (ResponseLevel.YELLOW, ResponseLevel.RED, ResponseLevel.EMERGENCY)


class InvalidAnswers(ValueError):
    pass


class NextStep(StrEnum):
    NONE = "none"
    RISK_BLOCK = "risk_block"
    SELF_USER_HELP = "self_user_help"  # у пользователя нет врача: только экран помощи (§3.1)


@dataclass(frozen=True)
class BlockAnswers:
    """Ответы «да/нет» уточняющего блока. None — вопрос не отвечен (не путать с «нет»)."""

    q1: bool | None = None  # пассивные мысли
    q2: bool | None = None  # активные мысли
    q3: bool | None = None  # способ
    q4: bool | None = None  # намерение
    q5: bool | None = None  # план
    q6: bool | None = None  # подготовка или попытка за 3 месяца

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> BlockAnswers:
        unknown = set(raw) - set(QUESTION_IDS)
        if unknown:
            raise InvalidAnswers(f"Неизвестные вопросы: {sorted(unknown)}")
        for key, value in raw.items():
            if value is not None and not isinstance(value, bool):
                raise InvalidAnswers(f"Ответ на {key} должен быть «да» или «нет»")
        answers = cls(**raw)  # type: ignore[arg-type]
        validate(answers)
        return answers

    def answered_ids(self) -> tuple[str, ...]:
        return tuple(f.name for f in fields(self) if getattr(self, f.name) is not None)


@dataclass(frozen=True)
class Assessment:
    outcome: AssessmentOutcome
    base_level: ResponseLevel
    final_level: ResponseLevel
    escalated_by_risk_factors: bool
    flag_level: FlagLevel
    flag_reason: FlagReason
    doctor_push: PushPriority
    patient_screen: str  # ключ экрана в content/instruments/suicide_block.*.json


def next_step_after_phq9(item9_value: int, *, has_treating_doctor: bool) -> NextStep:
    """Любой ответ на 9-й вопрос, кроме «Ни разу», запускает протокол независимо от суммы (§4.4)."""
    if item9_value == 0:
        return NextStep.NONE
    return NextStep.RISK_BLOCK if has_treating_doctor else NextStep.SELF_USER_HELP


def visible_questions(answers: BlockAnswers) -> tuple[str, ...]:
    if answers.q2 is True:
        return QUESTION_IDS
    return ("q1", "q2", "q6")


def validate(answers: BlockAnswers) -> None:
    if answers.q2 is not True:
        asked_without_q2 = [q for q in FOLLOW_UP_IDS if getattr(answers, q) is not None]
        if asked_without_q2:
            raise InvalidAnswers(f"{', '.join(asked_without_q2)} задаются только при ответе «да» на q2")


def outcome_of(answers: BlockAnswers) -> AssessmentOutcome:
    answered = answers.answered_ids()
    if not answered:
        return AssessmentOutcome.DISMISSED
    if all(q in answered for q in visible_questions(answers)):
        return AssessmentOutcome.ANSWERED
    return AssessmentOutcome.PARTIAL


def level_from_answers(answers: BlockAnswers) -> ResponseLevel:
    if answers.q4 or answers.q5 or answers.q6:
        return ResponseLevel.EMERGENCY
    if answers.q2:
        return ResponseLevel.RED
    # Пассивные мысли — жёлтый. Все ответы «нет» при q9 > 0 — тоже жёлтый (В1):
    # сигнал PHQ-9 не теряем, «низкого риска» не бывает.
    return ResponseLevel.YELLOW


def raise_one_step(level: ResponseLevel) -> ResponseLevel:
    index = _LEVEL_ORDER.index(level)
    return _LEVEL_ORDER[min(index + 1, len(_LEVEL_ORDER) - 1)]


def _max_level(a: ResponseLevel, b: ResponseLevel) -> ResponseLevel:
    return max(a, b, key=_LEVEL_ORDER.index)


def assess(answers: BlockAnswers, *, has_risk_factors: bool) -> Assessment:
    validate(answers)
    outcome = outcome_of(answers)

    if outcome is AssessmentOutcome.DISMISSED:
        # Неизвестность трактуется в сторону безопасности (§4.6).
        base = ResponseLevel.RED
    else:
        base = level_from_answers(answers)
        if outcome is AssessmentOutcome.PARTIAL:
            base = _max_level(base, ResponseLevel.RED)  # В3

    # Исходные факторы риска повышают уровень на ступень — в том числе при отказе отвечать (В2).
    final = raise_one_step(base) if has_risk_factors else base

    if outcome is AssessmentOutcome.DISMISSED:
        reason = FlagReason.RISK_BLOCK_DISMISSED
        screen = "dismissed"
    else:
        reason = {
            ResponseLevel.YELLOW: FlagReason.RISK_BLOCK_YELLOW,
            ResponseLevel.RED: FlagReason.RISK_BLOCK_RED,
            ResponseLevel.EMERGENCY: FlagReason.RISK_BLOCK_EMERGENCY,
        }[final]
        screen = final.value

    return Assessment(
        outcome=outcome,
        base_level=base,
        final_level=final,
        escalated_by_risk_factors=final != base,
        flag_level=FlagLevel.YELLOW if final is ResponseLevel.YELLOW else FlagLevel.RED,
        flag_reason=reason,
        doctor_push={
            ResponseLevel.YELLOW: PushPriority.NORMAL,
            ResponseLevel.RED: PushPriority.URGENT,
            ResponseLevel.EMERGENCY: PushPriority.IMMEDIATE,
        }[final],
        patient_screen=screen,
    )
