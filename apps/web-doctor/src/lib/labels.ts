// Подписи для врача. Красный/жёлтый/зелёный — только в кабинете врача (§1.1);
// на экранах пациента красные цвета запрещены (§5.7).

export const DISCLAIMER = "Прототип. Не предназначен для диагностики и лечения. Все данные демонстрационные.";

export const FLAG_REASON: Record<string, string> = {
  risk_block_emergency: "Уточняющий блок: экстренный уровень",
  risk_block_red: "Уточняющий блок: красный уровень",
  risk_block_dismissed: "Уточняющий блок закрыт без ответа",
  risk_block_yellow: "Уточняющий блок: пассивные мысли о смерти",
  panic_button: "Нажата тревожная кнопка",
  crisis_words: "Кризисные слова в сообщении",
  alarming_symptom: "Тревожный побочный симптом",
  phq9_increase: "PHQ-9 вырос на 5+ баллов",
  gad7_increase: "GAD-7 вырос на 4+ балла",
  missed_doses: "2+ пропуска приёма подряд",
  self_dose_change: "Пациент сам изменил дозу",
  low_mood_streak: "Настроение ≤ 3 три дня подряд",
  new_side_effect: "Новый побочный эффект",
  no_data: "Нет данных 7 дней",
};

export const COLOR_LABEL: Record<string, string> = { red: "Красный", yellow: "Жёлтый", green: "Зелёный" };

export const COLOR_DOT: Record<string, string> = {
  red: "bg-red-600",
  yellow: "bg-amber-400",
  green: "bg-emerald-500",
};

export const DIARY_METRICS: { key: string; label: string; max: number }[] = [
  { key: "mood", label: "Настроение", max: 10 },
  { key: "interest", label: "Интерес и удовольствие", max: 10 },
  { key: "anxiety", label: "Тревога", max: 10 },
  { key: "worry_control", label: "Контроль беспокойства", max: 10 },
  { key: "sleep_hours", label: "Сон, часы", max: 12 },
  { key: "sleep_quality", label: "Качество сна", max: 10 },
  { key: "energy", label: "Силы", max: 10 },
];

export const DOSE_STATUS: Record<string, string> = {
  taken: "Принял(а)",
  taken_late: "Принял(а) позже",
  missed: "Пропустил(а)",
  self_changed: "Изменил(а) дозу сам(а)",
  no_response: "Нет ответа",
};

export const RISK_LEVEL: Record<string, string> = { yellow: "Жёлтый", red: "Красный", emergency: "Экстренный" };

export const MARKER_KIND: Record<string, string> = { start: "Начало", dose_change: "Смена дозы", stop: "Отмена" };

export function formatDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow",
  });
}
