"""Демо-данные для презентации (§7.13). Все люди и данные вымышленные.

| Персонаж | Что показываем |
|---|---|
| Анна, 34, F32.1 — сертралин 50 → 100 мг через 2 недели, 6 недель дневника, PHQ-9 16 → 8 | Зелёный флаг, график с отметкой повышения дозы |
| Игорь, 41, F41.1 — эсциталопрам 10 мг, 3 пропуска подряд, GAD-7 +5, трамадол от другого врача | Жёлтый флаг, правило при пропуске |
| Мария, 27, F33.1 — венлафаксин, «Несколько дней» на 9-й вопрос PHQ-9 → уточняющий блок → красный | Протокол безопасности, план безопасности |
| Олег, 29 — пользователь без диагноза | Самопроверка проходится вживую: PHQ-9 = 12, GAD-7 = 7 |

История (дневник, прошлые опросники, отметки о приёме) вставляется напрямую, а последние события —
через те же сервисы, что и в приложении: флаги ставит настоящая логика, а не сид.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.content.models import Content
from app.core.security import new_invite_code
from app.domain.enums import (
    CareLinkStatus,
    ConsentKind,
    DoseStatus,
    InstrumentCode,
    MedsTaken,
    MissedDoseRule,
    NotificationStatus,
    RiskTrigger,
    Role,
    ScheduleStatus,
    Sex,
    SideEffectSource,
    SubmissionContext,
)
from app.domain.treatment import DoseResponse, Step
from app.models import (
    Account,
    CareLink,
    Consent,
    Diagnosis,
    DiaryEntry,
    DiarySideEffect,
    DoctorProfile,
    DoseEvent,
    Notification,
    PatientProfile,
    Prescription,
    QuestionnaireAnswer,
    QuestionnaireSchedule,
    QuestionnaireSubmission,
    SafetyPlan,
    SideEffectReport,
)
from app.services.assistant import add_other_medication
from app.services.auth import create_doctor
from app.services.doses import planned, respond_to_dose, steps_of
from app.services.questionnaires import submit_weekly
from app.services.reference_sync import sync_reference_tables
from app.services.risk_protocol import record_risk_assessment
from app.services.treatment import PrescriptionSpec, create_prescription

TZ = ZoneInfo("Europe/Moscow")
DEMO_DOCTOR_EMAIL = "doctor@demo.mindcare.test"
# Вымышленные номера из одного блока, чтобы их нельзя было спутать с настоящими пациентами.
LOGINS = {"anna": "+79000000001", "igor": "+79000000002", "maria": "+79000000003", "oleg": "+79000000004"}


class DemoAlreadySeeded(RuntimeError):
    pass


@dataclass(frozen=True)
class DemoPerson:
    key: str
    full_name: str
    login: str
    role: Role
    scenario: str


@dataclass(frozen=True)
class DemoSummary:
    doctor_email: str
    people: list[DemoPerson]


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=TZ)


def _birth_date(today: date, age: int) -> date:
    return date(today.year - age, today.month, min(today.day, 28)) - timedelta(days=40)


def _clamp(value: float) -> int:
    return int(max(0, min(10, round(value))))


def _half_hours(value: float) -> float:
    return max(0.0, min(24.0, round(value * 2) / 2))


def _answers(total: int, items: int, rng: random.Random, *, last: int | None = None) -> list[int]:
    """Ответы по пунктам с заданной суммой. last — фиксированный ответ на последний пункт (9-й PHQ-9)."""
    answers = [0] * items
    free = items if last is None else items - 1
    remaining = total - (last or 0)
    while remaining:
        i = rng.randrange(free)
        if answers[i] < 3:
            answers[i] += 1
            remaining -= 1
    if last is not None:
        answers[-1] = last
    return answers


class _Seeder:
    def __init__(self, db: Session, now: datetime, content: Content, rng: random.Random, doctor: DoctorProfile):
        self.db, self.now, self.content, self.rng, self.doctor = db, now, content, rng, doctor
        self.today = now.astimezone(TZ).date()

    # --- люди ---------------------------------------------------------------------------------

    def person(self, key: str, full_name: str, age: int, sex: Sex, *, linked_at: datetime | None,
               icd: str | None, role: Role = Role.PATIENT) -> PatientProfile:
        account = Account(role=role, phone=LOGINS[key], created_at=linked_at or self.now)
        self.db.add(account)
        self.db.flush()
        self.db.add(Consent(account_id=account.id, kind=ConsentKind.HEALTH_DATA, text_version=self.content.consent.version,
                            method="демо-данные", given_at=linked_at or self.now))
        patient = PatientProfile(account_id=account.id, full_name=full_name, birth_date=_birth_date(self.today, age),
                                 sex=sex, city="Москва", region_code="moscow",
                                 diary_reminder_time=time(20, 0) if role is Role.PATIENT else None,
                                 quiet_hours_start=time(23, 0), quiet_hours_end=time(8, 0),
                                 created_at=linked_at or self.now)
        self.db.add(patient)
        self.db.flush()
        if role is Role.PATIENT:
            self.db.add(CareLink(doctor_id=self.doctor.account_id, patient_id=patient.id, invite_code=new_invite_code(),
                                 invite_expires_at=linked_at, status=CareLinkStatus.ACTIVE, linked_at=linked_at))
            self.db.add(Diagnosis(patient_id=patient.id, classification=self.content.icd.classification, icd_code=icd,
                                  set_by=self.doctor.account_id, set_at=linked_at))
            self.db.flush()
        return patient

    def prescribe(self, patient: PatientProfile, start: date, **spec) -> Prescription:
        return create_prescription(
            self.db, doctor_account_id=self.doctor.account_id, patient_id=patient.id, now=_at(start, 10),
            content=self.content,
            spec=PrescriptionSpec(form="таблетки", unit="мг", times=[time(9, 0)], start_date=start,
                                  in_person_visit_date=start, **spec),
        )

    # --- история ------------------------------------------------------------------------------

    def dose_history(self, p: Prescription, patient: PatientProfile,
                     status_for: Callable[[int, datetime], DoseStatus]) -> None:
        for k, (at, dose) in enumerate(planned(p, patient, steps_of(self.db, p.id), _at(p.start_date, 0), self.now)):
            event = self.db.scalar(select(DoseEvent).where(DoseEvent.prescription_id == p.id,
                                                           DoseEvent.scheduled_at == at))
            if event is None:
                event = DoseEvent(prescription_id=p.id, patient_id=p.patient_id, scheduled_at=at, planned_dose=dose,
                                  status=DoseStatus.PENDING)
                self.db.add(event)
            status = status_for(k, at)
            if status is not DoseStatus.PENDING:
                event.status = status
                event.responded_at = at + (timedelta(hours=3) if status is DoseStatus.TAKEN_LATE else timedelta(minutes=5))
        self.db.flush()

    def diary(self, patient: PatientProfile, start: date, days: int, skip: set[int],
              values: Callable[[int, float], dict]) -> list[DiaryEntry]:
        """Пропущенные дни остаются пропусками: на графике — разрыв линии, а не ноль."""
        entries = []
        for i in range(days):
            if i in skip:
                continue
            day = start + timedelta(days=i)
            at = _at(day, 21)
            v = values(i, i / max(days - 1, 1))
            side_effects = v.pop("side_effects", [])
            entry = DiaryEntry(client_id=uuid.uuid4(), patient_id=patient.id, day=day, client_submitted_at=at,
                               submitted_at=at, **v)
            self.db.add(entry)
            self.db.flush()
            for code in side_effects:
                self.db.add(DiarySideEffect(entry_id=entry.id, code=code))
            entries.append(entry)
        self.db.flush()
        return entries

    def questionnaire(self, patient: PatientProfile, instrument: InstrumentCode, answers: list[int], at: datetime,
                      schedule_id: uuid.UUID | None) -> None:
        definition = self.content.instrument(instrument)
        submission = QuestionnaireSubmission(
            client_id=uuid.uuid4(), patient_id=patient.id, instrument=instrument, instrument_version=definition.version,
            context=SubmissionContext.WEEKLY, schedule_id=schedule_id, total_score=sum(answers),
            client_submitted_at=at, submitted_at=at)
        self.db.add(submission)
        self.db.flush()
        self.db.add_all(QuestionnaireAnswer(submission_id=submission.id, item_no=no, value=value)
                        for no, value in enumerate(answers, start=1))

    def weekly_history(self, patient: PatientProfile, start: date, phq9: list[int], gad7: list[int]) -> None:
        for week, (phq, gad) in enumerate(zip(phq9, gad7, strict=True)):
            day = start + timedelta(days=7 * week)
            at = min(_at(day, 12), self.now - timedelta(minutes=30))
            slot = QuestionnaireSchedule(patient_id=patient.id, due_date=day, status=ScheduleStatus.DONE, closed_at=at)
            self.db.add(slot)
            self.db.flush()
            self.questionnaire(patient, InstrumentCode.PHQ9, _answers(phq, 9, self.rng, last=0), at, slot.id)
            self.questionnaire(patient, InstrumentCode.GAD7, _answers(gad, 7, self.rng), at, slot.id)
        self.db.flush()

    def noise(self) -> float:
        return self.rng.uniform(-1, 1)


def _seed_anna(s: _Seeder) -> DemoPerson:
    start = s.today - timedelta(days=42)
    anna = s.person("anna", "Анна Демо", 34, Sex.FEMALE, linked_at=_at(start, 10), icd="F32.1")
    p = s.prescribe(anna, start, substance_id="sertraline", dose=Decimal(50), with_food="after",
                    instructions="После завтрака", missed_dose_rule=MissedDoseRule.SKIP_NO_DOUBLE,
                    titration=[Step(start + timedelta(days=14), Decimal(100))])
    s.dose_history(p, anna, lambda k, _: DoseStatus.TAKEN_LATE if k in (5, 19) else DoseStatus.TAKEN)

    def values(i: int, progress: float) -> dict:
        nausea = i < 6  # тошнота в первые дни приёма, потом проходит
        return dict(
            mood=_clamp(3 + 4 * progress + s.noise()), interest=_clamp(2 + 4 * progress + s.noise()),
            anxiety=_clamp(6 - 3 * progress + s.noise()), worry_control=_clamp(4 + 3 * progress + s.noise()),
            sleep_hours=_half_hours(5.5 + 2 * progress + s.rng.choice([-0.5, 0, 0.5])),
            sleep_quality=_clamp(4 + 3 * progress + s.noise()), energy=_clamp(3 + 4 * progress + s.noise()),
            meds_taken=MedsTaken.ALL, had_side_effects=nausea, side_effects=["nausea"] if nausea else [],
        )

    entries = s.diary(anna, start, 42, skip={9, 23, 30}, values=values)
    for n, entry in enumerate(e for e in entries if e.had_side_effects):
        s.db.add(SideEffectReport(patient_id=anna.id, code="nausea", source=SideEffectSource.DIARY,
                                  source_ref=entry.id, is_new=n == 0, reported_at=entry.submitted_at))
    s.weekly_history(anna, start, phq9=[16, 15, 13, 12, 11, 9, 8], gad7=[11, 10, 9, 8, 7, 7, 6])
    return DemoPerson("anna", anna.full_name, LOGINS["anna"], Role.PATIENT,
                      "Зелёный флаг; PHQ-9 16 → 8; на графике — повышение дозы до 100 мг")


def _seed_igor(s: _Seeder) -> DemoPerson:
    start = s.today - timedelta(days=35)
    igor = s.person("igor", "Игорь Демо", 41, Sex.MALE, linked_at=_at(start, 10), icd="F41.1")
    p = s.prescribe(igor, start, substance_id="escitalopram", dose=Decimal(10),
                    missed_dose_rule=MissedDoseRule.TAKE_IF_MORE_THAN_HOURS, missed_dose_hours=12)
    missed_days = {s.today - timedelta(days=k) for k in (3, 2, 1)}
    s.dose_history(p, igor, lambda _, at: DoseStatus.PENDING if at.astimezone(TZ).date() in missed_days
                   else DoseStatus.TAKEN)
    # Три пропуска подряд — через сервис: жёлтый флаг ставит правило §1.1, пациент видит правило врача.
    for day in sorted(missed_days):
        event = s.db.scalar(select(DoseEvent).where(DoseEvent.prescription_id == p.id,
                                                    DoseEvent.scheduled_at == _at(day, 9)))
        respond_to_dose(s.db, patient_id=igor.id, dose_event_id=event.id, response=DoseResponse.MISSED,
                        now=_at(day, 11), content=s.content)

    def values(i: int, progress: float) -> dict:
        day = start + timedelta(days=i)
        return dict(
            mood=_clamp(5 + s.noise()), interest=_clamp(4 + s.noise()), anxiety=_clamp(7 + progress + s.noise()),
            worry_control=_clamp(3 + s.noise()), sleep_hours=_half_hours(6 + s.rng.choice([-1, -0.5, 0, 0.5])),
            sleep_quality=_clamp(4 + s.noise()), energy=_clamp(5 + s.noise()),
            meds_taken=MedsTaken.MISSED if day in missed_days else MedsTaken.ALL, had_side_effects=False,
        )

    s.diary(igor, start, 35, skip={12, 27}, values=values)
    s.weekly_history(igor, start, phq9=[8, 7, 7, 6, 6], gad7=[9, 8, 8, 7, 7])
    # Последний GAD-7 — через сервис: рост на 5 баллов (7 → 12) ставит жёлтый флаг.
    submit_weekly(s.db, patient_id=igor.id, client_id=uuid.uuid4(), instrument=InstrumentCode.GAD7,
                  answers=_answers(12, 7, s.rng), client_submitted_at=s.now, now=s.now, content=s.content)
    # Блок 9: трамадол от другого врача — через ассистента: проверка взаимодействий и сообщение лечащему врачу.
    add_other_medication(s.db, patient=igor, substance_id="tramadol", free_name=None,
                         now=s.now - timedelta(days=2), content=s.content)
    return DemoPerson("igor", igor.full_name, LOGINS["igor"], Role.PATIENT,
                      "Жёлтый флаг: 3 пропуска подряд и GAD-7 +5; трамадол от другого врача")


def _seed_maria(s: _Seeder) -> DemoPerson:
    start = s.today - timedelta(days=21)
    maria = s.person("maria", "Мария Демо", 27, Sex.FEMALE, linked_at=_at(start, 10), icd="F33.1")
    p = s.prescribe(maria, start, substance_id="venlafaxine", dose=Decimal(75), with_food="after",
                    missed_dose_rule=MissedDoseRule.CONTACT_DOCTOR)
    s.dose_history(p, maria, lambda *_: DoseStatus.TAKEN)

    def values(i: int, progress: float) -> dict:
        return dict(
            mood=_clamp(4.5 - 1.5 * progress + s.noise()), interest=_clamp(3 - progress + s.noise()),
            anxiety=_clamp(6 + progress + s.noise()), worry_control=_clamp(4 - progress + s.noise()),
            sleep_hours=_half_hours(6 - progress + s.rng.choice([-0.5, 0, 0.5])),
            sleep_quality=_clamp(4 - progress + s.noise()), energy=_clamp(4 - progress + s.noise()),
            meds_taken=MedsTaken.ALL, had_side_effects=False,
        )

    s.diary(maria, start, 21, skip={15}, values=values)
    s.weekly_history(maria, start, phq9=[13, 14, 15], gad7=[10, 11, 12])
    s.db.add(SafetyPlan(
        patient_id=maria.id, version=1, updated_by=s.doctor.account_id, created_at=_at(start, 11),
        doctor_reviewed_at=_at(start, 11),
        warning_signs="Перестаю отвечать на сообщения, не встаю с кровати, мысли «всё бессмысленно»",
        coping_strategies="Выйти на улицу на 15 минут, тёплый душ, дыхание 4–7–8, музыка из плейлиста «Спокойно»",
        contacts=[{"name": "Сестра (демо)", "phone": "+79000000099"}],
        professionals=[{"name": "Лечащий врач — сообщение в приложении", "phone": None}],
        means_restriction="Лекарства хранит сестра и выдаёт на неделю",
    ))
    # Сегодня: PHQ-9 с ответом «Несколько дней» на 9-й вопрос → уточняющий блок → красный уровень.
    phq9 = submit_weekly(s.db, patient_id=maria.id, client_id=uuid.uuid4(), instrument=InstrumentCode.PHQ9,
                         answers=_answers(16, 9, s.rng, last=1), client_submitted_at=s.now, now=s.now,
                         content=s.content)
    submit_weekly(s.db, patient_id=maria.id, client_id=uuid.uuid4(), instrument=InstrumentCode.GAD7,
                  answers=_answers(12, 7, s.rng), client_submitted_at=s.now, now=s.now, content=s.content)
    record_risk_assessment(s.db, patient_id=maria.id, client_id=uuid.uuid4(), trigger=RiskTrigger.PHQ9_ITEM9,
                           trigger_ref=phq9.submission_id,
                           answers={"q1": True, "q2": True, "q3": False, "q4": False, "q5": False, "q6": False},
                           client_submitted_at=s.now, now=s.now, content=s.content)
    return DemoPerson("maria", maria.full_name, LOGINS["maria"], Role.PATIENT,
                      "Красный флаг: уточняющий блок после 9-го вопроса PHQ-9; план безопасности")


def _seed_oleg(s: _Seeder) -> DemoPerson:
    oleg = s.person("oleg", "Олег Демо", 29, Sex.MALE, linked_at=None, icd=None, role=Role.SELF_USER)
    return DemoPerson("oleg", oleg.full_name, LOGINS["oleg"], Role.SELF_USER,
                      "Самопроверка вживую: PHQ-9 = 12, GAD-7 = 7 → рекомендация и каталог")


def seed_demo(db: Session, *, now: datetime, content: Content, doctor_password: str, rng_seed: int = 713) -> DemoSummary:
    if db.scalar(select(Account.id).where(Account.email == DEMO_DOCTOR_EMAIL)) is not None:
        raise DemoAlreadySeeded("Демо-данные уже загружены — пересоздайте базу, чтобы загрузить заново")
    sync_reference_tables(db, content)
    doctor = create_doctor(db, email=DEMO_DOCTOR_EMAIL, password=doctor_password,
                           full_name="Иванова Елена Сергеевна (демо)", specialty="врач-психиатр")
    doctor.working_hours = {d: ["09:00", "18:00"] for d in ("mon", "tue", "wed", "thu", "fri")}
    doctor.response_time_hours = 24
    seeder = _Seeder(db, now, content, random.Random(rng_seed), doctor)
    people = [_seed_anna(seeder), _seed_igor(seeder), _seed_maria(seeder), _seed_oleg(seeder)]
    # Напоминания, «запланированные» в прошлом истории, не должны прийти пациентам при первом запуске воркера.
    db.execute(update(Notification)
               .where(Notification.status == NotificationStatus.SCHEDULED,
                      Notification.scheduled_for < now - timedelta(hours=1))
               .values(status=NotificationStatus.CANCELLED))
    db.flush()
    return DemoSummary(DEMO_DOCTOR_EMAIL, people)
