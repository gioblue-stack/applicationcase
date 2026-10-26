"""Перечисления предметной области.

Общие для доменных правил и моделей БД. Значения — стабильные строковые коды:
они хранятся в БД и передаются клиентам, поэтому их нельзя переименовывать без миграции.
"""

from enum import StrEnum


class Role(StrEnum):
    DOCTOR = "doctor"
    PATIENT = "patient"
    SELF_USER = "self_user"  # пользователь без диагноза и без врача (§3)


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class CareLinkStatus(StrEnum):
    PENDING = "pending"  # код-приглашение выдан, пациент ещё не подтвердил
    ACTIVE = "active"
    ENDED = "ended"


class ConsentKind(StrEnum):
    HEALTH_DATA = "health_data"  # ст. 10 152-ФЗ


class InstrumentCode(StrEnum):
    PHQ9 = "PHQ9"
    GAD7 = "GAD7"


class SubmissionContext(StrEnum):
    WEEKLY = "weekly"
    SELF_CHECK = "self_check"


class ScheduleStatus(StrEnum):
    PENDING = "pending"
    REMINDED = "reminded"
    DONE = "done"
    MISSED = "missed"


class MedsTaken(StrEnum):
    ALL = "all"
    MISSED = "missed"
    SELF_CHANGED = "self_changed"


class RiskTrigger(StrEnum):
    PHQ9_ITEM9 = "phq9_item9"
    UNSCHEDULED_MOOD_DROP = "unscheduled_mood_drop"
    UNSCHEDULED_VERY_LOW_MOOD = "unscheduled_very_low_mood"
    UNSCHEDULED_TREATMENT_CHANGE = "unscheduled_treatment_change"
    UNSCHEDULED_ADHERENCE = "unscheduled_adherence"
    UNSCHEDULED_INSOMNIA_ANXIETY = "unscheduled_insomnia_anxiety"
    ALARMING_SYMPTOM = "alarming_symptom"  # §7.5: «мысли о самоубийстве появились или усилились»


class AssessmentOutcome(StrEnum):
    ANSWERED = "answered"
    PARTIAL = "partial"  # начал отвечать и закрыл блок
    DISMISSED = "dismissed"  # «Не сейчас» / закрыл без ответа


class ResponseLevel(StrEnum):
    """Уровень реагирования (§4.6). Намеренно нет уровня ниже жёлтого: «низкий риск» не существует."""

    YELLOW = "yellow"
    RED = "red"
    EMERGENCY = "emergency"


class FlagLevel(StrEnum):
    RED = "red"
    YELLOW = "yellow"


class FlagStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"  # врач «взял в работу»
    AUTO_RESOLVED = "auto_resolved"  # только «нет данных 7 дней» при появлении данных (В6); остаётся в истории


class FlagReason(StrEnum):
    RISK_BLOCK_EMERGENCY = "risk_block_emergency"
    RISK_BLOCK_RED = "risk_block_red"
    RISK_BLOCK_DISMISSED = "risk_block_dismissed"
    RISK_BLOCK_YELLOW = "risk_block_yellow"
    PANIC_BUTTON = "panic_button"
    CRISIS_WORDS = "crisis_words"
    ALARMING_SYMPTOM = "alarming_symptom"
    PHQ9_INCREASE = "phq9_increase"
    GAD7_INCREASE = "gad7_increase"
    MISSED_DOSES = "missed_doses"
    SELF_DOSE_CHANGE = "self_dose_change"
    LOW_MOOD_STREAK = "low_mood_streak"
    NEW_SIDE_EFFECT = "new_side_effect"
    NO_DATA = "no_data"


class PushPriority(StrEnum):
    NORMAL = "normal"  # врач увидит в ближайший рабочий день
    URGENT = "urgent"  # срочное push-уведомление
    IMMEDIATE = "immediate"  # немедленное уведомление (экстренный уровень)


class DoseStatus(StrEnum):
    PENDING = "pending"
    TAKEN = "taken"
    TAKEN_LATE = "taken_late"
    MISSED = "missed"
    SELF_CHANGED = "self_changed"
    NO_RESPONSE = "no_response"  # «не знаем», а не «пропустил» (§1.2)


class MissedDoseRule(StrEnum):
    TAKE_IF_MORE_THAN_HOURS = "take_if_more_than_hours"
    SKIP_NO_DOUBLE = "skip_no_double"
    CONTACT_DOCTOR = "contact_doctor"


class RegimenChangeType(StrEnum):
    CREATED = "created"
    DOSE_CHANGED = "dose_changed"
    TITRATION_SHIFTED = "titration_shifted"
    EDITED = "edited"
    STOPPED = "stopped"


class OtherMedicationSource(StrEnum):
    OTHER_DOCTOR = "other_doctor"
    OTC = "otc"
    SUPPLEMENT = "supplement"


class LabEventStatus(StrEnum):
    SCHEDULED = "scheduled"
    DONE = "done"


class MessageDirection(StrEnum):
    PATIENT_TO_DOCTOR = "patient_to_doctor"
    DOCTOR_TO_PATIENT = "doctor_to_patient"


class MessageOrigin(StrEnum):
    BLOCK7_QUESTION = "block7_question"
    BLOCK9_OTHER_DOCTOR = "block9_other_doctor"
    STILL_ASK_DOCTOR = "still_ask_doctor"
    ASSISTANT_HANDOFF = "assistant_handoff"
    DOCTOR_REPLY = "doctor_reply"


class MessageStatus(StrEnum):
    NEW = "new"
    READ = "read"
    ANSWERED = "answered"


class SideEffectSource(StrEnum):
    DIARY = "diary"
    ASSISTANT = "assistant"


class NotificationKind(StrEnum):
    DOSE_REMINDER = "dose_reminder"
    DIARY_REMINDER = "diary_reminder"
    WEEKLY_QUESTIONNAIRE = "weekly_questionnaire"
    LAB_REMINDER = "lab_reminder"
    DOCTOR_REPLY = "doctor_reply"
    RED_FLAG = "red_flag"
    YELLOW_FLAG = "yellow_flag"


class NotificationStatus(StrEnum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditAction(StrEnum):
    VIEW = "view"
    CREATE = "create"
    UPDATE = "update"


class TextStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class InteractionSeverity(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    INFO = "info"
