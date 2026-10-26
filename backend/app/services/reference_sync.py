"""Перенос справочников из content/*.json в БД (идемпотентно, при деплое и в тестах)."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.content.models import Content
from app.models import AlarmingSymptom, HelpPhone, IcdCode, Instrument, InteractionRule, Substance


def _upsert(db: Session, model, rows: list[dict], keys: list[str]) -> None:
    if not rows:
        return
    stmt = insert(model).values(rows)
    updates = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
    db.execute(stmt.on_conflict_do_update(index_elements=keys, set_=updates))


def sync_reference_tables(db: Session, content: Content) -> None:
    _upsert(
        db,
        IcdCode,
        [{"classification": content.icd.classification, "code": c.code, "title": c.title} for c in content.icd.codes],
        ["classification", "code"],
    )
    _upsert(
        db,
        Substance,
        [
            {"id": d.id, "inn": d.inn, "group_label": d.group, "classes": d.classes, "in_formulary": True,
             "default_missed_dose_rule": None, "default_missed_dose_hours": None,
             "instruction": {"demo_notes": d.demo_notes} if d.demo_notes else None, "source": content.drugs.source}
            for d in content.drugs.drugs
        ]
        + [
            {"id": s.id, "inn": s.name, "group_label": s.category, "classes": s.classes, "in_formulary": False,
             "default_missed_dose_rule": None, "default_missed_dose_hours": None, "instruction": None,
             "source": content.interactions.source}
            for s in content.interactions.substances
        ],
        ["id"],
    )
    _upsert(
        db,
        InteractionRule,
        [
            {"id": r.id, "selector_a": r.a.model_dump(), "selector_b": r.b.model_dump(), "severity": r.severity,
             "patient_text": r.patient_text, "ask_doctor": r.ask_doctor, "source": r.risk}
            for r in content.interactions.rules
        ],
        ["id"],
    )
    _upsert(
        db,
        AlarmingSymptom,
        [
            {"code": s.code, "patient_text": s.patient_text, "doctor_meaning": s.doctor_meaning,
             "action": s.action, "flag_level": s.flag_level.value if s.flag_level else None}
            for s in content.alarming_symptoms.symptoms
        ],
        ["code"],
    )
    _upsert(
        db,
        HelpPhone,
        [
            {"id": p.id, "display": p.display, "tel": p.tel, "service": p.service, "region": p.region,
             "hours": p.hours, "verified_at": content.help_phones.verified_at}
            for p in content.help_phones.phones
        ],
        ["id"],
    )
    _upsert(
        db,
        Instrument,
        [
            {"code": i.code.value, "version": i.version, "definition": i.model_dump(mode="json")}
            for i in (content.phq9, content.gad7)
        ]
        + [{"code": "SRB", "version": content.suicide_block.version,
            "definition": content.suicide_block.model_dump(mode="json")},
           {"code": "DIARY", "version": content.diary.version, "definition": content.diary.model_dump(mode="json")}],
        ["code", "version"],
    )
    db.flush()
