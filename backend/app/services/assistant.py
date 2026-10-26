"""Цифровой ассистент (§2.3, §5.4): набор кнопок, у каждой заранее известен источник ответа.

[Д] данные пациента, [И] инструкция или база взаимодействий, [К] утверждённые тексты, [В] — сразу врачу.
Ассистент ничего не сочиняет и не советует менять или отменять лечение. Если данных нет, так и говорит
и предлагает передать вопрос врачу. Каждый ответ сохраняется: врач видит историю вопросов (§1.4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.models import AssistantButton, Content
from app.domain.crisis_words import CrisisMatcher, default_matcher
from app.domain.diary import SideEffectAnswer
from app.domain.enums import (
    FlagLevel,
    FlagReason,
    InstrumentCode,
    LabEventStatus,
    MessageOrigin,
    OtherMedicationSource,
    SideEffectSource,
    SubmissionContext,
)
from app.domain.flag_rules import FlagCandidate
from app.domain.interactions import Finding, SubstanceInfo, check_against, needs_doctor, substance_from_content
from app.domain.questionnaire_feedback import patient_feedback
from app.models import (
    AssistantInteraction,
    DoseEvent,
    LabEvent,
    LabOrder,
    OtherMedication,
    PatientProfile,
    Prescription,
    QuestionnaireSubmission,
    Substance,
)
from app.services import messages
from app.services.care import active_doctor_id, local_now
from app.services.diary import effective_entries
from app.services.flags import raise_flag
from app.services.screens import HelpScreen, help_screen_for
from app.services.thresholds import get_thresholds
from app.services.treatment import patient_plan

FOLLOW_UP = ["helped", "still_ask_doctor"]


class AssistantError(ValueError):
    pass


class InteractionNotFound(AssistantError, LookupError):
    pass


@dataclass(frozen=True)
class AnswerPart:
    source: str  # Д | И | К | В
    text: str
    reference: str | None = None  # откуда ответ: схема врача, демо-база §7.8, утверждённый текст


@dataclass(frozen=True)
class AssistantAnswer:
    interaction_id: uuid.UUID
    button_id: str
    label: str
    parts: list[AnswerPart]
    actions: list[str] = field(default_factory=list)
    handed_to_doctor: bool = False
    message_id: uuid.UUID | None = None
    offer_doctor: bool = False
    follow_up: list[str] = field(default_factory=lambda: list(FOLLOW_UP))
    choices: list[dict] | None = None
    findings: list[Finding] | None = None
    help_screen: HelpScreen | None = None


def _require_doctor(db: Session, patient: PatientProfile) -> None:
    if active_doctor_id(db, patient.id) is None:
        raise AssistantError("Ассистент доступен пациенту, подключённому к лечащему врачу")


def _text(content: Content, key: str) -> AnswerPart:
    t = content.approved_texts[key]
    approval = content.approved_texts.approval
    ref = (f"Утверждено: {approval.approved_by}, {approval.approved_at:%d.%m.%Y}" if approval.status == "approved"
           else approval.note)
    return AnswerPart("К", t.text, ref)


def _record(db: Session, patient: PatientProfile, button: AssistantButton, now: datetime, *, sources: list[str],
            ref: str | None, message_id: uuid.UUID | None) -> AssistantInteraction:
    interaction = AssistantInteraction(patient_id=patient.id, button_key=button.id, answer_sources=sources,
                                       answer_ref=ref, escalated_message_id=message_id, created_at=now)
    db.add(interaction)
    db.flush()
    return interaction


def _handoff_parts(db: Session, patient: PatientProfile, content: Content) -> list[AnswerPart]:
    preface = messages.preface(db, patient, content)
    deadline = f" Срок ответа — до {preface.response_time_hours} ч." if preface.response_time_hours else ""
    return [AnswerPart("В", content.approved_texts["handoff_done"].text + deadline),
            AnswerPart("В", preface.warning)]


# --- Обработчики [Д] -------------------------------------------------------------------------


def _plan_parts(db, patient, now, content, line) -> list[AnswerPart]:
    plan = patient_plan(db, patient.id, now, content)
    if not plan:
        return [_text(content, "no_medications")]
    return [AnswerPart("Д", line(item), "Схема лечения, внесённая врачом") for item in plan]


_FOOD = {"before": "до еды", "after": "после еды", "any": "независимо от еды"}


def _how_to_take(item) -> str:
    food = f", {_FOOD[item.with_food]}" if item.with_food in _FOOD else ""
    extra = f". {item.instructions}" if item.instructions else ""
    return f"{item.inn} {item.current_dose} {item.unit} — в {', '.join(item.times)}{food}{extra}"


def _progress(db, patient, now) -> list[AnswerPart]:
    today = local_now(patient, now).date()
    entries = effective_entries(db, patient.id, today - timedelta(days=13), today)
    week = [e.mood for d, e in entries.items() if d > today - timedelta(days=7) and e.mood is not None]
    before = [e.mood for d, e in entries.items() if d <= today - timedelta(days=7) and e.mood is not None]
    filled = sum(1 for d in entries if d > today - timedelta(days=7))
    text = f"За последние 7 дней вы отметили самочувствие {filled} из 7 дней."
    if week:
        text += f" Среднее настроение — {sum(week) / len(week):.1f}".replace(".", ",")
        if before:
            text += f" (неделей раньше — {sum(before) / len(before):.1f})".replace(".", ",")
        text += "."
    return [AnswerPart("Д", text, "Ваш дневник")]


def _latest_results(db, patient, content) -> list[AnswerPart]:
    t = get_thresholds(db, content)
    parts = []
    for code, key in ((InstrumentCode.PHQ9, "phq9_increase_yellow"), (InstrumentCode.GAD7, "gad7_increase_yellow")):
        superseded = select(QuestionnaireSubmission.supersedes_id).where(QuestionnaireSubmission.supersedes_id.is_not(None))
        rows = db.scalars(select(QuestionnaireSubmission).where(
            QuestionnaireSubmission.patient_id == patient.id, QuestionnaireSubmission.instrument == code,
            QuestionnaireSubmission.context == SubmissionContext.WEEKLY, QuestionnaireSubmission.id.not_in(superseded))
            .order_by(QuestionnaireSubmission.submitted_at.desc()).limit(2)).all()
        if rows:
            fb = patient_feedback(content.patient_texts, code, rows[0].total_score,
                                  rows[1].total_score if len(rows) > 1 else None, threshold=int(t[key]))
            parts.append(AnswerPart("Д", " ".join(x for x in (fb.result_text, fb.change_text) if x), "Ваши опросники"))
    if not parts:
        return [AnswerPart("Д", "Вы ещё не проходили еженедельные опросники.", "Ваши опросники")]
    return parts + [AnswerPart("Д", content.patient_texts.not_diagnosis_note)]


def _adherence(db, patient, now) -> list[AnswerPart]:
    since = now - timedelta(days=7)
    events = db.scalars(select(DoseEvent).where(DoseEvent.patient_id == patient.id, DoseEvent.scheduled_at >= since,
                                                DoseEvent.scheduled_at <= now)).all()
    taken = sum(e.status in ("taken", "taken_late") for e in events)
    if not events:
        return [AnswerPart("Д", "За последние 7 дней приёмов по схеме не было.", "Ваши отметки о приёме")]
    return [AnswerPart("Д", f"За последние 7 дней отмечено принятыми {taken} из {len(events)} приёмов.",
                       "Ваши отметки о приёме")]


def _labs(db, patient, now, content) -> list[AnswerPart]:
    today = local_now(patient, now).date()
    rows = db.execute(select(LabOrder.lab_type, LabEvent.due_date).join(LabEvent, LabEvent.order_id == LabOrder.id)
                      .where(LabOrder.patient_id == patient.id, LabEvent.status == LabEventStatus.SCHEDULED,
                             LabEvent.due_date >= today).order_by(LabEvent.due_date)).all()
    if not rows:
        return [_text(content, "no_labs")]
    return [AnswerPart("Д", f"{lab} — {due:%d.%m.%Y}", "Назначения врача") for lab, due in rows]


def _why_drug(db, patient, content) -> list[AnswerPart]:
    classes = set()
    for (cls,) in db.execute(select(Substance.classes).join(Prescription, Prescription.substance_id == Substance.id)
                             .where(Prescription.patient_id == patient.id, Prescription.stopped_at.is_(None))):
        classes |= set(cls)
    keys = [k for cond, k in ((bool(classes & {"antidepressant"}), "why_antidepressant"),
                              (bool(classes & {"anxiolytic", "benzodiazepine"}), "why_anxiolytic"),
                              (bool(classes & {"antipsychotic"}), "why_antipsychotic_low_dose")) if cond]
    if not keys:
        return [_text(content, "no_medications")]
    return [_text(content, k) for k in keys] + [
        AnswerPart("В", "Почему врач выбрал именно этот препарат — можно спросить врача.")]


def _instruction(db, patient, button, content) -> list[AnswerPart]:
    parts = []
    for p in db.scalars(select(Prescription).where(Prescription.patient_id == patient.id,
                                                   Prescription.stopped_at.is_(None))):
        section = ((db.get(Substance, p.substance_id).instruction or {}).get(button.section))
        if section:
            parts.append(AnswerPart("И", section, "Инструкция к препарату"))
    return parts or [AnswerPart("И", content.approved_texts["no_instruction_data"].text, "Демо-база препаратов §7.8")]


# --- Ответ на кнопку -------------------------------------------------------------------------


def answer(db: Session, *, patient: PatientProfile, button_id: str, now: datetime, content: Content) -> AssistantAnswer:
    _require_doctor(db, patient)
    button = content.assistant.button(button_id)
    if button is None:
        raise InteractionNotFound("Нет такого вопроса")
    h = button.handler
    parts: list[AnswerPart] = []
    actions: list[str] = []
    choices = None
    message_id = None

    if h == "text":
        parts = [_text(content, k) for k in button.text_keys]
    elif h == "handoff":
        message_id = messages.handoff(db, patient=patient, template_key=button.id, body=button.label, now=now).id
        parts = [_text(content, k) for k in button.text_keys] + _handoff_parts(db, patient, content)
    elif h == "action":
        actions = [button.action]
    elif h == "how_to_take":
        parts = _plan_parts(db, patient, now, content, _how_to_take) + _instruction(db, patient, button, content)
    elif h == "missed_dose_rule":
        parts = _plan_parts(db, patient, now, content, lambda i: f"{i.inn}: {i.missed_dose_rule_text}")
        parts.append(AnswerPart("Д", content.treatment_texts.rule_author_note))
    elif h == "current_meds":
        parts = _plan_parts(db, patient, now, content,
                            lambda i: f"{i.inn} {i.current_dose} {i.unit} — {', '.join(i.times)}")
    elif h == "upcoming_changes":
        plan = patient_plan(db, patient.id, now, content)
        lines = [f"{i.inn}: {step}" for i in plan for step in i.upcoming]
        parts = [AnswerPart("Д", line, "Схема лечения, внесённая врачом") for line in lines] or [
            _text(content, "no_upcoming")]
    elif h == "next_visit_and_labs":
        parts = [_text(content, "no_visit_data")] + _labs(db, patient, now, content)
    elif h == "why_drug":
        parts = _why_drug(db, patient, content)
    elif h == "progress":
        parts, actions = _progress(db, patient, now), ["open_progress"]
    elif h == "latest_results":
        parts = _latest_results(db, patient, content)
    elif h == "adherence":
        parts = _adherence(db, patient, now)
    elif h == "labs_list":
        parts = _labs(db, patient, now, content)
    elif h == "instruction":
        parts = _instruction(db, patient, button, content)
    elif h == "choose_substance":
        actions = ["choose_substance"]
        choices = [{"id": s.id, "name": s.name, "category": s.category} for s in content.interactions.substances] + [
            {"id": d.id, "name": d.inn, "category": "drug"} for d in content.drugs.drugs]
    elif h == "choose_side_effect":
        actions = ["choose_side_effect"]
        choices = [c.model_dump() for c in content.assistant.side_effect_choices]
    elif h == "choose_alarming_symptom":
        actions = ["choose_alarming_symptom"]
        choices = [{"code": s.code, "label": s.patient_text} for s in content.alarming_symptoms.symptoms]

    sources = list(button.sources)
    interaction = _record(db, patient, button, now, sources=sources, ref=h, message_id=message_id)
    return AssistantAnswer(interaction.id, button.id, button.label, parts, actions, message_id is not None, message_id,
                           button.offer_doctor, choices=choices)


# --- Взаимодействия и другие препараты -------------------------------------------------------


def _patient_substances(db: Session, patient_id: uuid.UUID, content: Content) -> list[SubstanceInfo]:
    result = []
    for (sid,) in db.execute(select(Prescription.substance_id).where(Prescription.patient_id == patient_id,
                                                                     Prescription.stopped_at.is_(None))):
        result.append(substance_from_content(content, sid))
    for m in db.scalars(select(OtherMedication).where(OtherMedication.patient_id == patient_id,
                                                      OtherMedication.removed_at.is_(None))):
        known = substance_from_content(content, m.substance_id) if m.substance_id else None
        result.append(known or SubstanceInfo(None, m.free_name or "Препарат"))
    return [s for s in result if s is not None]


def _resolve(content: Content, substance_id: str | None, free_name: str | None) -> SubstanceInfo:
    if substance_id:
        info = substance_from_content(content, substance_id)
        if info is None:
            raise InteractionNotFound("Нет такого вещества в базе")
        return info
    name = (free_name or "").strip()
    if not name or len(name) > 100:
        raise AssistantError("Укажите название препарата (до 100 знаков)")
    return SubstanceInfo(None, name)


def _finding_parts(findings: list[Finding]) -> list[AnswerPart]:
    return [AnswerPart("И", f"{f.first} + {f.second}: {f.patient_text}", "Демо-база взаимодействий §7.8")
            for f in findings]


def check_combination(db: Session, *, patient: PatientProfile, substance_id: str | None, free_name: str | None,
                      now: datetime, content: Content) -> AssistantAnswer:
    """«Можно ли принимать вместе с…». Опасное сочетание или нет данных — вопрос сразу врачу [В]."""
    _require_doctor(db, patient)
    new = _resolve(content, substance_id, free_name)
    current = _patient_substances(db, patient.id, content)
    if not current:
        findings = []
        parts = [_text(content, "no_medications")]
    else:
        findings = check_against(new, current, content)
        parts = _finding_parts(findings)
    button = content.assistant.button("combine")
    message_id = None
    if needs_doctor(findings):
        message_id = messages.handoff(db, patient=patient, template_key="combine",
                                      body=f"{button.label} {new.name}?", now=now).id
        parts += _handoff_parts(db, patient, content)
    interaction = _record(db, patient, button, now, sources=["И", "В"] if message_id else ["И"], ref=new.id or new.name,
                          message_id=message_id)
    return AssistantAnswer(interaction.id, button.id, button.label, parts, [], message_id is not None, message_id,
                           findings=findings)


def add_other_medication(db: Session, *, patient: PatientProfile, substance_id: str | None, free_name: str | None,
                         now: datetime, content: Content,
                         source: OtherMedicationSource = OtherMedicationSource.OTHER_DOCTOR) -> AssistantAnswer:
    """Блок 9: препарат в «другие препараты» → проверка взаимодействий → уведомление лечащему врачу."""
    _require_doctor(db, patient)
    new = _resolve(content, substance_id, free_name)
    findings = check_against(new, _patient_substances(db, patient.id, content), content)
    db.add(OtherMedication(patient_id=patient.id, substance_id=new.id, free_name=None if new.id else new.name,
                           source=source, added_at=now))
    warnings = [f for f in findings if f.severity in ("red", "yellow")]
    summary = (f"предупреждений: {len(warnings)}" if warnings else
               "данных о сочетании нет" if any(f.severity == "unknown" for f in findings) else "предупреждений нет")
    message = messages.handoff(db, patient=patient, template_key="new_drug", now=now,
                               origin=MessageOrigin.BLOCK9_OTHER_DOCTOR,
                               body=f"Добавлен препарат от другого врача: {new.name}. Проверка взаимодействий: {summary}.")
    button = content.assistant.button("new_drug")
    parts = _finding_parts(findings) + _handoff_parts(db, patient, content)
    interaction = _record(db, patient, button, now, sources=["И", "В"], ref=new.id or new.name, message_id=message.id)
    return AssistantAnswer(interaction.id, button.id, button.label, parts, [], True, message.id, findings=findings)


# --- Побочные эффекты (блок 2) ---------------------------------------------------------------


def report_side_effect(db: Session, *, patient: PatientProfile, code: str, other_text: str | None, now: datetime,
                       content: Content, matcher: CrisisMatcher | None = None) -> AssistantAnswer:
    from app.services.side_effects import record_side_effects

    _require_doctor(db, patient)
    choice = next((c for c in content.assistant.side_effect_choices if c.code == code), None)
    if choice is None:
        raise InteractionNotFound("Нет такого варианта")
    text = (other_text or "").strip() or None
    if choice.free_text and not text:
        raise AssistantError("Опишите, что именно беспокоит")
    if text and (not choice.free_text or len(text) > int(get_thresholds(db, content)["free_text_max_chars"])):
        raise AssistantError("Текст нужен только для «Другое» и не длиннее 500 знаков")
    record_side_effects(db, patient_id=patient.id, items=[SideEffectAnswer(code, text)],
                        source=SideEffectSource.ASSISTANT, source_ref=None, now=now)
    help_screen = None
    if text and (matcher or default_matcher()).is_crisis(text):
        raise_flag(db, FlagCandidate(FlagLevel.RED, FlagReason.CRISIS_WORDS, f"crisis_words:assistant:{uuid.uuid4()}"),
                   patient_id=patient.id, source_type="side_effect_report", source_id=None, now=now)
        help_screen = help_screen_for(content, patient.region_code, has_doctor=True)
    button = content.assistant.button("side_effect")
    parts = [AnswerPart("И", content.approved_texts["no_instruction_data"].text, "Демо-база препаратов §7.8"),
             AnswerPart("Д", content.approved_texts["side_effect_recorded"].text)]
    interaction = _record(db, patient, button, now, sources=["И"], ref=code, message_id=None)
    return AssistantAnswer(interaction.id, button.id, button.label, parts, [], offer_doctor=True,
                           help_screen=help_screen)


def feedback(db: Session, *, patient: PatientProfile, interaction_id: uuid.UUID, helped: bool) -> None:
    """«Ответ помог» / «Всё равно хочу спросить врача»."""
    interaction = db.get(AssistantInteraction, interaction_id)
    if interaction is None or interaction.patient_id != patient.id:
        raise InteractionNotFound("Ответ ассистента не найден")
    interaction.helped = helped
    db.flush()


# --- История для врача -----------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryItem:
    interaction_id: uuid.UUID
    button_id: str
    label: str
    sources: list[str]
    helped: bool | None
    escalated_message_id: uuid.UUID | None
    created_at: datetime


@dataclass(frozen=True)
class AssistantHistory:
    items: list[HistoryItem]
    week_counts: dict[str, int]  # сколько раз за 7 дней — «5 вопросов про отмену за неделю» уже сигнал (§1.4)


def history(db: Session, patient_id: uuid.UUID, *, now: datetime, content: Content) -> AssistantHistory:
    rows = db.scalars(select(AssistantInteraction).where(AssistantInteraction.patient_id == patient_id)
                      .order_by(AssistantInteraction.created_at.desc())).all()
    labels = {b.id: b.label for block in content.assistant.blocks for b in block.buttons}
    counts: dict[str, int] = {}
    for r in rows:
        if r.created_at >= now - timedelta(days=7):
            counts[r.button_key] = counts.get(r.button_key, 0) + 1
    return AssistantHistory(
        [HistoryItem(r.id, r.button_key, labels.get(r.button_key, r.button_key), list(r.answer_sources), r.helped,
                     r.escalated_message_id, r.created_at) for r in rows],
        counts,
    )

