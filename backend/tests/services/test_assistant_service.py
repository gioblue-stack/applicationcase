"""Ассистент на демо-данных §7.13."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.content.loader import load_content
from app.domain.enums import FlagReason, FlagStatus
from app.models import AssistantInteraction, Flag, Message, PatientProfile, SideEffectReport
from app.seed.demo import seed_demo
from app.services import assistant

CONTENT = load_content()
NOW = datetime(2026, 10, 26, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))


@pytest.fixture
def people(db):
    summary = seed_demo(db, now=NOW, content=CONTENT, doctor_password="demo password 2026")
    return {p.key: db.scalar(select(PatientProfile).where(PatientProfile.full_name == p.full_name))
            for p in summary.people}


def ask(db, patient, button, now=NOW):
    return assistant.answer(db, patient=patient, button_id=button, now=now, content=CONTENT)


def texts(answer):
    return [(p.source, p.text) for p in answer.parts]


def test_how_to_take_uses_doctors_scheme_and_admits_missing_instruction(db, people):
    result = ask(db, people["anna"], "how_to_take")
    assert texts(result)[0] == ("Д", "Сертралин 100 мг — в 09:00, после еды. После завтрака")
    assert texts(result)[1] == ("И", CONTENT.approved_texts["no_instruction_data"].text)


def test_missed_dose_shows_doctors_rule(db, people):
    result = ask(db, people["igor"], "missed_dose")
    assert result.parts[0].text.startswith("Эсциталопрам: Примите пропущенную дозу, если до следующего приёма больше 12 ч")
    assert result.parts[-1].text == "Это правило задал ваш лечащий врач."


def test_k_text_is_marked_as_draft_until_approved(db, people):
    [part] = ask(db, people["anna"], "onset").parts
    assert part.source == "К" and part.text.startswith("Антидепрессанты действуют постепенно")
    assert "требует утверждения" in part.reference


def test_reduce_or_stop_goes_straight_to_doctor_and_is_counted(db, people):
    igor = people["igor"]
    first = ask(db, igor, "reduce_or_stop")
    assert first.handed_to_doctor and first.message_id
    assert first.parts[0].text.startswith("Не снижайте дозу и не отменяйте препарат самостоятельно")
    assert any("не канал экстренной связи" in p.text for p in first.parts)
    message = db.get(Message, first.message_id)
    assert (message.template_key, message.body) == ("reduce_or_stop", "Хочу снизить дозу или отменить препарат")
    ask(db, igor, "reduce_or_stop")
    history = assistant.history(db, igor.id, now=NOW, content=CONTENT)
    assert history.week_counts["reduce_or_stop"] == 2  # «5 вопросов про отмену за неделю» — сигнал для врача


def test_data_answers(db, people):
    assert texts(ask(db, people["maria"], "current_meds")) == [("Д", "Венлафаксин 75 мг — 09:00")]
    assert texts(ask(db, people["anna"], "upcoming")) == [("К", "Изменений дозы врач пока не запланировал.")]
    assert ask(db, people["igor"], "adherence").parts[0].text == "За последние 7 дней отмечено принятыми 4 из 7 приёмов."
    results = [p.text for p in ask(db, people["anna"], "results").parts]
    assert results[0].startswith("Симптомы немного беспокоят") and "почти не изменились" in results[0]
    assert results[-1] == "Результаты опросников — не диагноз, их обсуждают с врачом."


def test_why_drug_explains_group_and_offers_doctor(db, people):
    result = ask(db, people["igor"], "why_drug")
    assert result.parts[0].text.startswith("Препараты, которые влияют на работу систем мозга")
    assert result.parts[-1].source == "В" and result.offer_doctor


def test_actions_for_crisis_and_safety_plan(db, people):
    assert ask(db, people["maria"], "feel_very_bad").actions == ["panic"]
    assert ask(db, people["maria"], "hard_day").actions == ["open_safety_plan"]


def test_unknown_button_and_self_user(db, people):
    with pytest.raises(assistant.InteractionNotFound):
        ask(db, people["anna"], "make_me_feel_better")
    with pytest.raises(assistant.AssistantError, match="лечащему врачу"):
        ask(db, people["oleg"], "onset")


def combine(db, patient, substance_id=None, free_name=None):
    return assistant.check_combination(db, patient=patient, substance_id=substance_id, free_name=free_name, now=NOW,
                                       content=CONTENT)


def test_combination_red_goes_to_doctor(db, people):
    result = combine(db, people["maria"], "maoi")
    assert [(f.severity, f.patient_text) for f in result.findings] == [("red", "Не принимайте вместе")]
    assert result.handed_to_doctor


def test_combination_outside_base_never_says_yes(db, people):
    result = combine(db, people["anna"], free_name="Парацетамол")
    assert [f.patient_text for f in result.findings] == ["Данных о сочетании нет"]
    assert result.handed_to_doctor
    assert all("можно" not in p.text.lower() for p in result.parts)


def test_combination_igor_alcohol_with_tramadol_unknown(db, people):
    result = combine(db, people["igor"], "alcohol")
    assert [f.severity for f in result.findings] == ["unknown", "info"]  # трамадол+алкоголь: правила нет


def test_new_drug_from_other_doctor_checked_and_reported(db, people):
    anna = people["anna"]
    result = assistant.add_other_medication(db, patient=anna, substance_id="aspirin", free_name=None, now=NOW,
                                            content=CONTENT)
    assert [(f.severity, f.rule_id) for f in result.findings] == [("yellow", "bleeding")]
    message = db.get(Message, result.message_id)
    assert message.origin == "block9_other_doctor"
    assert message.body == "Добавлен препарат от другого врача: Аспирин. Проверка взаимодействий: предупреждений: 1."


def test_side_effects_from_assistant(db, people):
    maria = people["maria"]
    assistant.report_side_effect(db, patient=maria, code="weight_gain", other_text=None, now=NOW, content=CONTENT)
    report = db.scalars(select(SideEffectReport).where(SideEffectReport.patient_id == maria.id)).one()
    assert (report.code, report.source, report.is_new) == ("weight_gain", "assistant", True)
    with pytest.raises(assistant.AssistantError, match="Опишите"):
        assistant.report_side_effect(db, patient=maria, code="other", other_text=" ", now=NOW, content=CONTENT)
    crisis = assistant.report_side_effect(db, patient=maria, code="other", other_text="хочу умереть от этой тошноты",
                                          now=NOW + timedelta(minutes=1), content=CONTENT)
    assert crisis.help_screen.key == "help"
    reasons = set(db.scalars(select(Flag.reason).where(Flag.patient_id == maria.id, Flag.status == FlagStatus.OPEN)))
    assert FlagReason.CRISIS_WORDS in reasons


def test_feedback(db, people):
    result = ask(db, people["anna"], "what_helps")
    assistant.feedback(db, patient=people["anna"], interaction_id=result.interaction_id, helped=True)
    assert db.get(AssistantInteraction, result.interaction_id).helped is True
    with pytest.raises(assistant.InteractionNotFound):
        assistant.feedback(db, patient=people["igor"], interaction_id=result.interaction_id, helped=False)
