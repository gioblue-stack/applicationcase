"""Схемы клинического контента из content/*.json.

Валидация здесь — защита от тихой порчи медицинских текстов и порогов:
приложение не стартует, если контент не согласован с доменной логикой.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.enums import FlagLevel, InstrumentCode, MedsTaken, MissedDoseRule, TextStatus
from app.domain.risk_protocol import FOLLOW_UP_IDS, QUESTION_IDS


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Approval(_Strict):
    status: TextStatus
    approved_by: str | None = None
    approved_at: date | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _approved_has_signature(self) -> Approval:
        if self.status is TextStatus.APPROVED and not (self.approved_by and self.approved_at):
            raise ValueError("Утверждённый текст должен содержать ФИО врача и дату утверждения")
        return self


class Option(_Strict):
    value: int
    label: str


class Item(_Strict):
    no: int
    text: str


class Band(_Strict):
    min: int
    max: int
    label: str


class Difficulty(_Strict):
    text: str
    options: list[Option]


class InstrumentDef(_Strict):
    code: InstrumentCode
    version: str
    title: str
    source: str
    instruction: str
    options: list[Option]
    items: list[Item]
    difficulty: Difficulty | None
    copyright: str
    safety_item: int | None
    max_total: int
    severity_bands_doctor_only: list[Band]

    @model_validator(mode="after")
    def _consistent(self) -> InstrumentDef:
        if [item.no for item in self.items] != list(range(1, len(self.items) + 1)):
            raise ValueError(f"{self.code}: пункты должны идти по порядку с 1")
        if [o.value for o in self.options] != [0, 1, 2, 3]:
            raise ValueError(f"{self.code}: варианты ответа должны иметь баллы 0–3")
        if self.max_total != 3 * len(self.items):
            raise ValueError(f"{self.code}: max_total не соответствует числу пунктов")
        expected_min = 0
        for band in self.severity_bands_doctor_only:
            if band.min != expected_min:
                raise ValueError(f"{self.code}: диапазоны выраженности должны идти без разрывов")
            expected_min = band.max + 1
        if expected_min != self.max_total + 1:
            raise ValueError(f"{self.code}: диапазоны выраженности не покрывают всю шкалу")
        if self.safety_item is not None and not 1 <= self.safety_item <= len(self.items):
            raise ValueError(f"{self.code}: safety_item вне списка пунктов")
        return self


class BlockQuestion(_Strict):
    id: str
    measures: str
    shown_if: dict[str, bool] | None
    text: str


class Intro(_Strict):
    text: str
    buttons: dict[str, str]
    show_help_phones: bool


class AnswerOption(_Strict):
    value: bool
    label: str


class Screen(_Strict):
    text: str
    fullscreen: bool
    actions: list[str]
    source: str | None = None


REQUIRED_SCREENS = ("yellow", "red", "emergency", "dismissed", "help", "self_user_help")


class SuicideBlockDef(_Strict):
    code: str
    version: str
    title: str
    source: str
    approval: Approval
    intro: Intro
    answer_options: list[AnswerOption]
    questions: list[BlockQuestion]
    screens: dict[str, Screen]
    action_labels: dict[str, str]

    @model_validator(mode="after")
    def _matches_domain(self) -> SuicideBlockDef:
        if tuple(q.id for q in self.questions) != QUESTION_IDS:
            raise ValueError("Вопросы блока должны совпадать с доменными q1–q6 и идти по порядку")
        for q in self.questions:
            expected = {"q2": True} if q.id in FOLLOW_UP_IDS else None
            if q.shown_if != expected:
                raise ValueError(f"{q.id}: условие показа не совпадает с протоколом §4.6")
        missing = set(REQUIRED_SCREENS) - set(self.screens)
        if missing:
            raise ValueError(f"Нет итоговых экранов: {sorted(missing)}")
        for key, screen in self.screens.items():
            unknown = set(screen.actions) - set(self.action_labels)
            if unknown:
                raise ValueError(f"Экран {key}: неизвестные действия {sorted(unknown)}")
        if not self.intro.show_help_phones:
            raise ValueError("Телефоны помощи должны быть видны уже на вступительном экране (§7.1)")
        if not self.screens["emergency"].fullscreen:
            raise ValueError("Экстренный экран должен быть на весь экран (§4.6)")
        return self


class HelpPhone(_Strict):
    id: str
    display: str
    tel: str
    service: str
    region: str
    hours: str


class HelpPhones(_Strict):
    source: str
    verified_at: date
    verification_note: str
    always_show: list[str]
    helpline_default: str
    phones: list[HelpPhone]

    @model_validator(mode="after")
    def _known_ids(self) -> HelpPhones:
        ids = {p.id for p in self.phones}
        if "112" not in self.always_show:
            raise ValueError("112 обязателен на экране помощи")
        unknown = (set(self.always_show) | {self.helpline_default}) - ids
        if unknown:
            raise ValueError(f"Неизвестные номера: {sorted(unknown)}")
        return self


class Thresholds(_Strict):
    source: str
    approval: Approval
    values: dict[str, int | float]

    def __getitem__(self, key: str) -> int | float:
        return self.values[key]


DIARY_QUESTION_IDS = ("mood", "interest", "anxiety", "worry_control", "sleep", "energy", "meds_taken", "side_effects")


class DiaryOption(_Strict):
    value: str
    label: str


class DiaryQuestion(_Strict):
    id: str
    no: int
    type: str
    text: str
    min_label: str | None = None
    max_label: str | None = None
    hours_step: float | None = None
    quality_min_label: str | None = None
    quality_max_label: str | None = None
    medication_only: bool = False
    options: list[DiaryOption] | None = None


class SideEffectOption(_Strict):
    code: str
    label: str
    free_text: bool = False


class DiaryDef(_Strict):
    code: str
    version: str
    source: str
    approval: Approval
    invitation: str
    questions: list[DiaryQuestion]
    side_effect_options: list[SideEffectOption]
    late_fill_note: str

    @model_validator(mode="after")
    def _consistent(self) -> DiaryDef:
        if tuple(q.id for q in self.questions) != DIARY_QUESTION_IDS:
            raise ValueError("Вопросы дневника должны совпадать с §4.3 и идти по порядку")
        meds = next(q for q in self.questions if q.id == "meds_taken")
        if [o.value for o in meds.options or []] != [m.value for m in MedsTaken]:
            raise ValueError("Варианты вопроса 7 должны совпадать со статусами MedsTaken")
        if not all(q.medication_only for q in self.questions if q.id in ("meds_taken", "side_effects")):
            raise ValueError("Вопросы 7 и 8 скрываются, если пациент не принимает лекарства (§4.3)")
        if not any(o.code == "other" and o.free_text for o in self.side_effect_options):
            raise ValueError("В вопросе 8 нужен вариант «Другое» с текстом")
        return self

    @property
    def side_effect_codes(self) -> set[str]:
        return {o.code for o in self.side_effect_options}


class TextBand(_Strict):
    min: int
    max: int
    text: str


class SelfCheckText(_Strict):
    text: str
    actions: list[str]


class SelfCheckTexts(_Strict):
    screening_note: str
    none: SelfCheckText
    mild: SelfCheckText
    pronounced: SelfCheckText


class PatientTexts(_Strict):
    source: str
    approval: Approval
    not_diagnosis_note: str
    result_bands: dict[InstrumentCode, list[TextBand]]
    change: dict[str, str]
    self_check: SelfCheckTexts

    @model_validator(mode="after")
    def _consistent(self) -> PatientTexts:
        for code, max_total in ((InstrumentCode.PHQ9, 27), (InstrumentCode.GAD7, 21)):
            expected_min = 0
            for band in self.result_bands[code]:
                if band.min != expected_min:
                    raise ValueError(f"{code}: тексты результатов должны покрывать шкалу без разрывов")
                expected_min = band.max + 1
            if expected_min != max_total + 1:
                raise ValueError(f"{code}: тексты результатов не покрывают всю шкалу")
        if set(self.change) != {"improved", "unchanged", "worse"}:
            raise ValueError("Нужны тексты изменения: improved, unchanged, worse")
        return self


class CrisisGroup(_Strict):
    id: str
    title: str
    phrases: list[str]


class WordForm(_Strict):
    phrase: str
    form_of: str


class CrisisWordForms(_Strict):
    note: str
    phrases: list[WordForm]


class CrisisWords(_Strict):
    source: str
    approval: Approval
    rules: dict[str, int | bool]
    groups: list[CrisisGroup]
    word_forms: CrisisWordForms

    @model_validator(mode="after")
    def _forms_refer_to_listed_phrases(self) -> CrisisWords:
        listed = {p for g in self.groups for p in g.phrases}
        unknown = [f.form_of for f in self.word_forms.phrases if f.form_of not in listed]
        if unknown:
            raise ValueError(f"Словоформы ссылаются на фразы не из списка §7.4: {unknown}")
        return self

    def group_of(self, phrase: str) -> str:
        return next(g.id for g in self.groups if phrase in g.phrases)


class AlarmingSymptomDef(_Strict):
    code: str
    patient_text: str
    doctor_meaning: str
    action: str
    flag_level: FlagLevel | None


RISK_PROTOCOL_ACTION = "risk_protocol"


class AlarmingSymptoms(_Strict):
    source: str
    approval: Approval
    symptoms: list[AlarmingSymptomDef]
    action_texts: dict[str, str]

    @model_validator(mode="after")
    def _consistent(self) -> AlarmingSymptoms:
        for s in self.symptoms:
            if s.action == RISK_PROTOCOL_ACTION:
                if s.flag_level is not None:
                    raise ValueError(f"{s.code}: уровень задаёт протокол безопасности, а не список")
            elif s.action not in self.action_texts or s.flag_level is None:
                raise ValueError(f"{s.code}: нужен текст действия и уровень флага")
        return self

    def by_code(self, code: str) -> AlarmingSymptomDef:
        for s in self.symptoms:
            if s.code == code:
                return s
        raise KeyError(code)


class DrugDef(_Strict):
    id: str
    inn: str
    group: str
    classes: list[str]
    demo_notes: str | None


class DrugsDemo(_Strict):
    source: str
    approval: Approval
    default_missed_dose_rule_note: str
    drugs: list[DrugDef]

    def by_id(self, drug_id: str) -> DrugDef:
        return next(d for d in self.drugs if d.id == drug_id)


class ReminderTexts(_Strict):
    title: str
    body_neutral: str
    body_detailed: str

    @model_validator(mode="after")
    def _neutral_has_no_details(self) -> ReminderTexts:
        if "{" in self.title or "{" in self.body_neutral:
            raise ValueError("Нейтральное напоминание не может содержать название препарата или дозу (§2.2)")
        return self


class TreatmentTexts(_Strict):
    source: str
    approval: Approval
    reminder: ReminderTexts
    responses: dict[str, str]
    snooze_minutes: list[int]
    snooze_label: str
    missed_dose_rules: dict[MissedDoseRule, str]
    missed_dose_hints: dict[str, str]
    rule_author_note: str
    plan_step: str

    @model_validator(mode="after")
    def _all_rules_have_texts(self) -> TreatmentTexts:
        if set(self.missed_dose_rules) != set(MissedDoseRule):
            raise ValueError("Нужен текст для каждого правила при пропуске")
        if set(self.missed_dose_hints) != {"take_now", "skip_now"}:
            raise ValueError("Нужны подсказки take_now и skip_now")
        for text in self.missed_dose_rules.values():
            if "Двойную дозу не принимайте" not in text:
                raise ValueError("Каждое правило при пропуске предупреждает о двойной дозе")
        return self


class ConsentDef(_Strict):
    source: str
    approval: Approval
    version: str
    title: str
    disclaimer: str
    paragraphs: list[str]


class IcdCodeDef(_Strict):
    code: str
    title: str


class IcdSubset(_Strict):
    source: str
    classification: str
    codes: list[IcdCodeDef]


ASSISTANT_HANDLERS = {
    "text", "handoff", "action", "how_to_take", "missed_dose_rule", "choose_substance", "instruction",
    "choose_side_effect", "choose_alarming_symptom", "current_meds", "upcoming_changes", "next_visit_and_labs",
    "why_drug", "progress", "latest_results", "adherence", "labs_list",
}


class AssistantButton(_Strict):
    id: str
    label: str
    sources: list[Literal["Д", "И", "К", "В"]]
    handler: str
    text: str | None = None
    texts: list[str] | None = None
    section: str | None = None
    action: str | None = None
    choices: list[str] | None = None
    offer_doctor: bool = False

    @property
    def text_keys(self) -> list[str]:
        return self.texts or ([self.text] if self.text else [])


class AssistantBlock(_Strict):
    no: int
    title: str
    always: bool = False
    buttons: list[AssistantButton]


class AssistantTree(_Strict):
    source: str
    follow_up: dict[str, str]
    blocks: list[AssistantBlock]
    side_effect_choices: list[SideEffectOption]

    @model_validator(mode="after")
    def _consistent(self) -> AssistantTree:
        if [b.no for b in self.blocks] != list(range(1, 10)):
            raise ValueError("Ассистент: нужны блоки 1–9 (§5.4)")
        if not next(b for b in self.blocks if b.no == 7).always:
            raise ValueError("Блок 7 «Связаться с врачом» есть всегда")
        ids = [btn.id for b in self.blocks for btn in b.buttons]
        if len(ids) != len(set(ids)):
            raise ValueError("Ассистент: повторяющиеся id кнопок")
        for b in self.blocks:
            for btn in b.buttons:
                if btn.handler not in ASSISTANT_HANDLERS:
                    raise ValueError(f"{btn.id}: неизвестный обработчик {btn.handler}")
                if btn.handler == "action" and not btn.action:
                    raise ValueError(f"{btn.id}: не указано действие")
        if set(self.follow_up) != {"helped", "still_ask_doctor"}:
            raise ValueError("После каждого ответа — «Ответ помог» / «Всё равно хочу спросить врача» (§5.4)")
        return self

    def button(self, button_id: str) -> AssistantButton | None:
        return next((btn for b in self.blocks for btn in b.buttons if btn.id == button_id), None)


class ApprovedTextDef(_Strict):
    source: str
    text: str


class ApprovedTexts(_Strict):
    source: str
    approval: Approval
    texts: dict[str, ApprovedTextDef]

    def __getitem__(self, key: str) -> ApprovedTextDef:
        return self.texts[key]


class InteractionSubstance(_Strict):
    id: str
    name: str
    classes: list[str]
    category: Literal["drug", "otc", "supplement", "alcohol"]


class InteractionSelector(_Strict):
    substances: list[str] = []
    classes: list[str] = []
    formulary: bool = False


class InteractionRuleDef(_Strict):
    id: str
    a: InteractionSelector
    b: InteractionSelector
    severity: Literal["red", "yellow", "info"]
    risk: str
    patient_text: str
    ask_doctor: bool


class InteractionRules(_Strict):
    source: str
    approval: Approval
    unknown_text: str
    substances: list[InteractionSubstance]
    rules: list[InteractionRuleDef]


class Content(_Strict):
    phq9: InstrumentDef
    gad7: InstrumentDef
    suicide_block: SuicideBlockDef
    help_phones: HelpPhones
    thresholds: Thresholds
    diary: DiaryDef
    patient_texts: PatientTexts
    crisis_words: CrisisWords
    alarming_symptoms: AlarmingSymptoms
    drugs: DrugsDemo
    treatment_texts: TreatmentTexts
    consent: ConsentDef
    icd: IcdSubset
    assistant: AssistantTree
    approved_texts: ApprovedTexts
    interactions: InteractionRules

    @model_validator(mode="after")
    def _cross_references(self) -> Content:
        for b in self.assistant.blocks:
            for btn in b.buttons:
                missing = [k for k in btn.text_keys if k not in self.approved_texts.texts]
                if missing:
                    raise ValueError(f"Кнопка {btn.id}: нет текстов {missing}")
        known = {d.id for d in self.drugs.drugs} | {s.id for s in self.interactions.substances}
        for rule in self.interactions.rules:
            unknown = (set(rule.a.substances) | set(rule.b.substances)) - known
            if unknown:
                raise ValueError(f"Правило {rule.id}: неизвестные вещества {sorted(unknown)}")
        return self

    def instrument(self, code: InstrumentCode) -> InstrumentDef:
        return {InstrumentCode.PHQ9: self.phq9, InstrumentCode.GAD7: self.gad7}[code]
