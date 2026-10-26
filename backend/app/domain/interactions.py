"""Проверка лекарственных взаимодействий по демо-базе (§2.3, §7.8).

Главное правило: если сочетания нет в базе — «Данных о сочетании нет» и вопрос врачу.
Ответа «можно» не существует: отсутствие правила не означает безопасность.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.content.models import Content, InteractionRuleDef, InteractionSelector

SEVERITY_ORDER = {"red": 0, "yellow": 1, "unknown": 2, "info": 3}


@dataclass(frozen=True)
class SubstanceInfo:
    """Вещество для проверки. id=None — пациент ввёл название, которого нет в базе."""

    id: str | None
    name: str
    classes: frozenset[str] = frozenset()
    formulary: bool = False


@dataclass(frozen=True)
class Finding:
    first: str
    second: str
    severity: str  # red | yellow | info | unknown
    patient_text: str
    risk: str | None  # пояснение для врача
    ask_doctor: bool
    rule_id: str | None


def substance_from_content(content: Content, substance_id: str) -> SubstanceInfo | None:
    for drug in content.drugs.drugs:
        if drug.id == substance_id:
            return SubstanceInfo(drug.id, drug.inn, frozenset(drug.classes), formulary=True)
    for s in content.interactions.substances:
        if s.id == substance_id:
            return SubstanceInfo(s.id, s.name, frozenset(s.classes))
    return None


def _matches(selector: InteractionSelector, s: SubstanceInfo) -> bool:
    if s.id is None:
        return False
    return (selector.formulary and s.formulary) or s.id in selector.substances or bool(s.classes & set(selector.classes))


def _rule_applies(rule: InteractionRuleDef, x: SubstanceInfo, y: SubstanceInfo) -> bool:
    return (_matches(rule.a, x) and _matches(rule.b, y)) or (_matches(rule.a, y) and _matches(rule.b, x))


def check_pair(x: SubstanceInfo, y: SubstanceInfo, content: Content) -> list[Finding]:
    found = [
        Finding(x.name, y.name, r.severity, r.patient_text, r.risk, r.ask_doctor, r.id)
        for r in content.interactions.rules if _rule_applies(r, x, y)
    ]
    if not found:
        found = [Finding(x.name, y.name, "unknown", content.interactions.unknown_text, None, True, None)]
    return sorted(found, key=lambda f: SEVERITY_ORDER[f.severity])


def check_against(new: SubstanceInfo, existing: Iterable[SubstanceInfo], content: Content) -> list[Finding]:
    """Новое вещество против всего, что пациент уже принимает. Самое опасное — первым."""
    findings = [f for other in existing if other.id is None or other.id != new.id
                for f in check_pair(new, other, content)]
    return sorted(findings, key=lambda f: SEVERITY_ORDER[f.severity])


def needs_doctor(findings: Iterable[Finding]) -> bool:
    return any(f.ask_doctor for f in findings)
