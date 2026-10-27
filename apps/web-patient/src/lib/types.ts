// Ответы API пациента (backend/app/api/routers/patient.py, content.py) — только то, что использует сайт.

export type Phone = { id: string; display: string; tel: string; service: string; region: string; hours: string };

export type HelpScreen = {
  key: string;
  text: string;
  fullscreen: boolean;
  actions: { action: string; label: string }[];
  phones: Phone[];
  helpline: Phone;
};

export type Option = { value: number; label: string };

export type Instrument = {
  code: "PHQ9" | "GAD7";
  title: string;
  instruction: string;
  options: Option[];
  items: { no: number; text: string }[];
  difficulty?: { text: string; options: Option[] };
  copyright?: string;
};

export type DiaryQuestion = {
  id: string;
  no: number;
  type: "scale" | "sleep" | "meds" | "side_effects";
  text: string;
  min_label?: string;
  max_label?: string;
  quality_min_label?: string;
  quality_max_label?: string;
  hours_step?: number;
  medication_only?: boolean;
  options?: { value: string; label: string }[];
};

export type DiaryContent = {
  invitation: string;
  questions: DiaryQuestion[];
  side_effect_options: { code: string; label: string; free_text?: boolean }[];
};

export type RiskQuestion = { id: string; text: string; shown_if: Record<string, boolean> | null };

export type Bootstrap = {
  disclaimer: string;
  consent: { version: string; title: string; paragraphs: string[] };
  help_phones: { always_show: string[]; helpline_default: string; phones: Phone[] };
  suicide_block: {
    intro: { text: string; buttons: { answer: string; dismiss: string } };
    answer_options: { value: boolean; label: string }[];
    questions: RiskQuestion[];
    screens: Record<string, { text: string; fullscreen: boolean; actions: string[] }>;
    action_labels: Record<string, string>;
  };
  instruments: { PHQ9: Instrument; GAD7: Instrument; DIARY: DiaryContent };
};

export type Me = {
  patient_id: string;
  full_name: string;
  has_doctor: boolean;
  takes_medication: boolean;
  region_code: string | null;
};

export type Today = {
  day: string;
  diary_entry_id: string | null;
  weekly: { due_date: string; pending: ("PHQ9" | "GAD7")[] } | null;
  risk_block_trigger: string | null;
};

export type Dose = {
  id: string;
  scheduled_at: string;
  local_time: string;
  inn: string;
  trade_name: string | null;
  dose: string;
  unit: string;
  status: "pending" | "taken" | "taken_late" | "missed" | "self_changed" | "no_response";
  answerable: boolean;
  snoozed_until: string | null;
};

export type DoseResult = {
  status: Dose["status"];
  guidance: { rule_text: string; hint_text: string | null; author_note: string } | null;
  offer_risk_block: string | null;
};

export type PlanItem = {
  prescription_id: string;
  inn: string;
  trade_name: string | null;
  form: string;
  current_dose: string;
  unit: string;
  times: string[];
  with_food: string | null;
  instructions: string | null;
  upcoming: string[];
  missed_dose_rule_text: string;
};

export type Contact = { name: string; phone: string | null };

export type SafetyPlan = {
  version: number;
  warning_signs: string | null;
  coping_strategies: string | null;
  contacts: Contact[];
  professionals: Contact[];
  means_restriction: string | null;
  updated_at: string;
  doctor_reviewed_at: string | null;
};

export type Message = {
  id: string;
  direction: string;
  body: string;
  status: string;
  created_at: string;
};

/** Лекарство без приёмов в выбранный день и его ближайший приём (GET /me/doses/next). */
export type NextDose = {
  prescription_id: string;
  inn: string;
  trade_name: string | null;
  dose: string;
  unit: string;
  scheduled_at: string;
  local_date: string;
  local_time: string;
};
