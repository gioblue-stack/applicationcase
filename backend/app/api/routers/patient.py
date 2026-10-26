"""API приложения пациента и пользователя: всё — от имени текущего пользователя (/me)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from typing import Literal

from fastapi import APIRouter, Response, UploadFile, status
from pydantic import BaseModel, Field, StrictBool, StrictInt

from app.api.deps import DB, AppSettings, ContentDep, CurrentPatient, Now
from app.content.models import AssistantTree
from app.domain.diary import DiaryAnswers, SideEffectAnswer
from app.domain.enums import InstrumentCode, MedsTaken, MessageOrigin, RiskTrigger
from app.domain.treatment import DoseResponse
from app.models.communication import MAX_ATTACHMENT_BYTES
from app.services import (
    assistant,
    attachments,
    diary,
    doses,
    messages,
    questionnaires,
    risk_protocol,
    safety_plan,
    side_effects,
    treatment,
)
from app.services.care import active_doctor_id

router = APIRouter(prefix="/me", tags=["Пациент"])


@router.get("")
def me(patient: CurrentPatient, db: DB) -> dict:
    return {"patient_id": patient.id, "full_name": patient.full_name,
            "has_doctor": active_doctor_id(db, patient.id) is not None,
            "takes_medication": patient.takes_medication, "region_code": patient.region_code}


class SideEffectIn(BaseModel):
    code: str = Field(max_length=64)
    other_text: str | None = Field(None, max_length=500)


class DiaryIn(BaseModel):
    client_id: uuid.UUID
    day: date
    client_submitted_at: datetime
    supersedes_id: uuid.UUID | None = None
    mood: StrictInt | None = None
    interest: StrictInt | None = None
    anxiety: StrictInt | None = None
    worry_control: StrictInt | None = None
    sleep_hours: float | None = None
    sleep_quality: StrictInt | None = None
    energy: StrictInt | None = None
    meds_taken: MedsTaken | None = None
    had_side_effects: StrictBool | None = None
    side_effects: list[SideEffectIn] = Field(default_factory=list, max_length=7)


@router.post("/diary", response_model=diary.DiaryResult, status_code=status.HTTP_201_CREATED)
def submit_diary(body: DiaryIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    answers = DiaryAnswers(
        **body.model_dump(include={"mood", "interest", "anxiety", "worry_control", "sleep_hours", "sleep_quality",
                                   "energy", "meds_taken", "had_side_effects"}),
        side_effects=tuple(SideEffectAnswer(s.code, s.other_text) for s in body.side_effects),
    )
    result = diary.submit_diary(db, patient_id=patient.id, client_id=body.client_id, day=body.day, answers=answers,
                                client_submitted_at=body.client_submitted_at, supersedes_id=body.supersedes_id,
                                now=now, content=content)
    db.commit()
    return result


@router.get("/diary/meds-suggestion")
def meds_suggestion(day: date, patient: CurrentPatient, db: DB) -> dict:
    return {"meds_taken": diary.suggest_meds_taken_for_day(db, patient.id, day)}


class WeeklyIn(BaseModel):
    client_id: uuid.UUID
    instrument: InstrumentCode
    answers: list[StrictInt] = Field(max_length=9)
    difficulty: StrictInt | None = None
    supersedes_id: uuid.UUID | None = None
    client_submitted_at: datetime


@router.post("/questionnaires", response_model=questionnaires.WeeklyResult, status_code=status.HTTP_201_CREATED)
def submit_questionnaire(body: WeeklyIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    result = questionnaires.submit_weekly(
        db, patient_id=patient.id, client_id=body.client_id, instrument=body.instrument, answers=body.answers,
        difficulty=body.difficulty, supersedes_id=body.supersedes_id, client_submitted_at=body.client_submitted_at,
        now=now, content=content)
    db.commit()
    return result


class SelfCheckIn(BaseModel):
    phq9_client_id: uuid.UUID
    gad7_client_id: uuid.UUID
    phq9_answers: list[StrictInt] = Field(max_length=9)
    gad7_answers: list[StrictInt] = Field(max_length=7)
    difficulty: StrictInt | None = None
    client_submitted_at: datetime


@router.post("/self-check", response_model=questionnaires.SelfCheckResult, status_code=status.HTTP_201_CREATED)
def self_check(body: SelfCheckIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    result = questionnaires.submit_self_check(
        db, patient_id=patient.id, phq9_client_id=body.phq9_client_id, gad7_client_id=body.gad7_client_id,
        phq9_answers=body.phq9_answers, gad7_answers=body.gad7_answers, difficulty=body.difficulty,
        client_submitted_at=body.client_submitted_at, now=now, content=content)
    db.commit()
    return result


class RiskAssessmentIn(BaseModel):
    client_id: uuid.UUID
    trigger: RiskTrigger
    trigger_ref: uuid.UUID | None = None
    answers: dict[str, StrictBool | None] = Field(default_factory=dict, description="Пусто — «Не сейчас»")
    started_at: datetime | None = None
    client_submitted_at: datetime


@router.post("/risk-assessments", response_model=risk_protocol.RiskAssessmentResult,
             status_code=status.HTTP_201_CREATED)
def risk_assessment(body: RiskAssessmentIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    result = risk_protocol.record_risk_assessment(
        db, patient_id=patient.id, client_id=body.client_id, trigger=body.trigger, trigger_ref=body.trigger_ref,
        answers=body.answers, started_at=body.started_at, client_submitted_at=body.client_submitted_at,
        now=now, content=content)
    db.commit()
    return result


class AlarmingSymptomIn(BaseModel):
    code: str = Field(max_length=64)


@router.post("/alarming-symptoms", response_model=side_effects.AlarmingSymptomResult,
             status_code=status.HTTP_201_CREATED)
def alarming_symptom(body: AlarmingSymptomIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    result = side_effects.report_alarming_symptom(db, patient_id=patient.id, code=body.code, now=now,
                                                  content=content)
    db.commit()
    return result


@router.get("/plan", response_model=list[treatment.PlanItem])
def plan(patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    return treatment.patient_plan(db, patient.id, now, content)


class DoseAnswerIn(BaseModel):
    response: DoseResponse
    actual_dose: Decimal | None = Field(None, gt=0)


@router.post("/doses/{dose_event_id}/response", response_model=doses.DoseResponseResult)
def answer_dose(dose_event_id: uuid.UUID, body: DoseAnswerIn, patient: CurrentPatient, db: DB, now: Now,
                content: ContentDep):
    result = doses.respond_to_dose(db, patient_id=patient.id, dose_event_id=dose_event_id, response=body.response,
                                   actual_dose=body.actual_dose, now=now, content=content)
    db.commit()
    return result


class SnoozeIn(BaseModel):
    minutes: StrictInt


@router.post("/doses/{dose_event_id}/snooze")
def snooze(dose_event_id: uuid.UUID, body: SnoozeIn, patient: CurrentPatient, db: DB, now: Now,
           content: ContentDep) -> dict:
    until = doses.snooze_dose(db, patient_id=patient.id, dose_event_id=dose_event_id, minutes=body.minutes,
                              now=now, content=content)
    db.commit()
    return {"snoozed_until": until}


@router.get("/unscheduled-block")
def unscheduled_block(patient: CurrentPatient, db: DB, now: Now, content: ContentDep) -> dict:
    """Нужно ли сегодня предложить уточняющий блок из-за старта/смены дозы антидепрессанта."""
    return {"trigger": doses.due_treatment_change_block(db, patient_id=patient.id, now=now, content=content)}


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(None, pattern=r"^\+?[0-9 ()-]{3,20}$")


class SafetyPlanIn(BaseModel):
    """План безопасности (§2.5): свои сигналы, способы справиться, люди и специалисты, ограничение доступа к средствам."""

    warning_signs: str | None = Field(None, max_length=1000)
    coping_strategies: str | None = Field(None, max_length=1000)
    contacts: list[ContactIn] = Field(default_factory=list, max_length=10)
    professionals: list[ContactIn] = Field(default_factory=list, max_length=10)
    means_restriction: str | None = Field(None, max_length=1000)


@router.get("/safety-plan", response_model=safety_plan.SafetyPlanView | None)
def get_safety_plan(patient: CurrentPatient, db: DB):
    """Приложение кэширует план на устройстве: он открывается на экране помощи без интернета."""
    return safety_plan.current_plan(db, patient.id)


@router.put("/safety-plan", response_model=safety_plan.SafetyPlanView)
def save_safety_plan(body: SafetyPlanIn, patient: CurrentPatient, db: DB, now: Now):
    data = safety_plan.SafetyPlanInput(
        warning_signs=body.warning_signs, coping_strategies=body.coping_strategies,
        contacts=[safety_plan.Contact(c.name, c.phone) for c in body.contacts],
        professionals=[safety_plan.Contact(c.name, c.phone) for c in body.professionals],
        means_restriction=body.means_restriction,
    )
    result = safety_plan.save_by_patient(db, patient=patient, data=data, now=now)
    db.commit()
    return result


# --- Ассистент (§5.4) ------------------------------------------------------------------------


@router.get("/assistant", response_model=AssistantTree)
def assistant_tree(patient: CurrentPatient, content: ContentDep):
    return content.assistant


class AssistantQuestionIn(BaseModel):
    button_id: str = Field(max_length=64)


@router.post("/assistant/answers", response_model=assistant.AssistantAnswer)
def assistant_answer(body: AssistantQuestionIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    result = assistant.answer(db, patient=patient, button_id=body.button_id, now=now, content=content)
    db.commit()
    return result


class SubstanceIn(BaseModel):
    """Вещество из базы (substance_id) или название, которого в базе нет (free_name)."""

    substance_id: str | None = Field(None, max_length=64)
    free_name: str | None = Field(None, max_length=100)


@router.post("/assistant/combinations", response_model=assistant.AssistantAnswer)
def assistant_combination(body: SubstanceIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    result = assistant.check_combination(db, patient=patient, substance_id=body.substance_id,
                                         free_name=body.free_name, now=now, content=content)
    db.commit()
    return result


class SideEffectReportIn(BaseModel):
    code: str = Field(max_length=64)
    other_text: str | None = Field(None, max_length=500)


@router.post("/assistant/side-effects", response_model=assistant.AssistantAnswer)
def assistant_side_effect(body: SideEffectReportIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    result = assistant.report_side_effect(db, patient=patient, code=body.code, other_text=body.other_text, now=now,
                                          content=content)
    db.commit()
    return result


class FeedbackIn(BaseModel):
    helped: StrictBool


@router.post("/assistant/interactions/{interaction_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def assistant_feedback(interaction_id: uuid.UUID, body: FeedbackIn, patient: CurrentPatient, db: DB) -> Response:
    assistant.feedback(db, patient=patient, interaction_id=interaction_id, helped=body.helped)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/other-medications", response_model=assistant.AssistantAnswer, status_code=status.HTTP_201_CREATED)
def add_other_medication(body: SubstanceIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    """Блок 9: «Мне назначили новый препарат» — проверка взаимодействий и уведомление врачу."""
    result = assistant.add_other_medication(db, patient=patient, substance_id=body.substance_id,
                                            free_name=body.free_name, now=now, content=content)
    db.commit()
    return result


# --- Сообщения врачу -------------------------------------------------------------------------


@router.get("/messages/preface", response_model=messages.MessagePreface)
def message_preface(patient: CurrentPatient, db: DB, content: ContentDep):
    """Срок ответа и предупреждение «Это не канал экстренной связи…» — до отправки вопроса (§2.4)."""
    return messages.preface(db, patient, content)


@router.get("/messages", response_model=list[messages.MessageView])
def my_messages(patient: CurrentPatient, db: DB):
    return messages.thread(db, patient.id)


class MessageIn(BaseModel):
    client_id: uuid.UUID
    origin: Literal["block7_question", "block9_other_doctor", "still_ask_doctor"]
    body: str = Field(max_length=2000)
    assistant_interaction_id: uuid.UUID | None = None


@router.post("/messages", response_model=messages.SentMessage, status_code=status.HTTP_201_CREATED)
def send_message(body: MessageIn, patient: CurrentPatient, db: DB, now: Now, content: ContentDep):
    result = messages.send_from_patient(db, patient=patient, client_id=body.client_id,
                                        origin=MessageOrigin(body.origin), body=body.body, now=now, content=content,
                                        assistant_interaction_id=body.assistant_interaction_id)
    db.commit()
    return result


@router.post("/messages/{message_id}/attachments", response_model=messages.AttachmentView,
             status_code=status.HTTP_201_CREATED)
async def attach(message_id: uuid.UUID, file: UploadFile, patient: CurrentPatient, db: DB, now: Now,
                 settings: AppSettings):
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    stored = attachments.store(db, patient=patient, message_id=message_id, data=data, settings=settings, now=now)
    db.commit()
    return messages.AttachmentView(stored.id, stored.mime, stored.size_bytes)
