"use client";
// Разделы карточки: факторы риска (§4.6, заполняет врач), история изменений схемы, вопросы ассистенту (§1.4),
// внешние факторы стресса (заполняет пациент при первом входе).
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { formatDateTime } from "@/lib/labels";
import type { AssistantHistory, RegimenChange, RiskFactors, StressView } from "@/lib/types";

const FACTORS: { key: keyof RiskFactors; label: string }[] = [
  { key: "prior_suicide_attempt", label: "Суицидальная попытка в прошлом" },
  { key: "self_harm", label: "Самоповреждения" },
  { key: "family_suicide", label: "Суицид у родственников" },
  { key: "substance_abuse", label: "Злоупотребление алкоголем или ПАВ" },
  { key: "recent_psychiatric_discharge", label: "Недавняя выписка из психиатрического стационара" },
  { key: "lives_alone", label: "Живёт один / одна" },
  { key: "chronic_pain_or_severe_illness", label: "Хроническая боль или тяжёлое соматическое заболевание" },
];

export function RiskFactorsForm({ patientId, initial, onError }: {
  patientId: string; initial: Record<string, unknown> | null; onError: (m: string) => void;
}) {
  const [values, setValues] = useState<RiskFactors>(() =>
    Object.fromEntries(FACTORS.map((f) => [f.key, Boolean(initial?.[f.key])])) as RiskFactors);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await api(`doctor/patients/${patientId}/risk-factors`, { method: "PUT", body: values });
      setSaved("Сохранено. Уровень следующих уточняющих блоков учтёт эти факторы.");
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded border bg-white p-3 text-sm">
      <p className="mb-2 text-slate-600">При наличии факторов уровень уточняющего блока повышается на ступень.</p>
      <div className="grid gap-1 sm:grid-cols-2">
        {FACTORS.map((f) => (
          <label key={f.key} className="flex items-center gap-2">
            <input type="checkbox" checked={Boolean(values[f.key])}
                   onChange={(e) => { setValues({ ...values, [f.key]: e.target.checked }); setSaved(null); }} />
            {f.label}
          </label>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-3">
        <button onClick={save} disabled={busy} className="rounded bg-slate-800 px-3 py-1 text-white">Сохранить</button>
        {saved && <span className="text-emerald-700">{saved}</span>}
      </div>
    </div>
  );
}

const CHANGE_LABEL: Record<RegimenChange["change_type"], string> = {
  created: "Назначен", dose_changed: "Изменена доза", titration_shifted: "Сдвинута титрация", edited: "Изменён",
  stopped: "Отменён",
};

function describe(state: Record<string, unknown> | null) {
  if (!state) return "—";
  const times = Array.isArray(state.times) ? state.times.join(", ") : "";
  return `${state.dose ?? ""} ${state.unit ?? ""}${times && `, ${times}`}`;
}

/** names: prescription_id → МНН (из приверженности, где есть и отменённые назначения). */
export function RegimenHistory({ patientId, names }: { patientId: string; names: Record<string, string> }) {
  const [items, setItems] = useState<RegimenChange[] | null>(null);
  useEffect(() => {
    api<RegimenChange[]>(`doctor/patients/${patientId}/regimen-history`).then(setItems).catch(() => setItems([]));
  }, [patientId, names]);

  if (!items) return null;
  if (items.length === 0) return <p className="text-sm text-slate-500">Изменений не было.</p>;
  return (
    <ul className="divide-y rounded border bg-white text-sm">
      {[...items].reverse().map((c) => (
        <li key={c.id} className="p-2">
          <span className="text-slate-500">{formatDateTime(c.changed_at)}</span> — <b>{CHANGE_LABEL[c.change_type]}</b>:{" "}
          {names[c.prescription_id] ?? String(c.after?.substance_id ?? c.before?.substance_id ?? "препарат")}
          {c.change_type === "created" ? ` ${describe(c.after)}` : ` ${describe(c.before)} → ${describe(c.after)}`}
          {c.reason && <span className="text-slate-600"> · {c.reason}</span>}
        </li>
      ))}
    </ul>
  );
}

const SOURCE: Record<string, string> = { "Д": "данные", "И": "инструкция", "К": "текст", "В": "врачу" };

export function AssistantLog({ patientId }: { patientId: string }) {
  const [history, setHistory] = useState<AssistantHistory | null>(null);
  useEffect(() => {
    api<AssistantHistory>(`doctor/patients/${patientId}/assistant-history`).then(setHistory).catch(() => null);
  }, [patientId]);

  if (!history) return null;
  if (history.items.length === 0) return <p className="text-sm text-slate-500">Пациент ещё не задавал вопросов.</p>;
  const labels = Object.fromEntries(history.items.map((i) => [i.button_id, i.label]));
  const frequent = Object.entries(history.week_counts).filter(([, n]) => n >= 3); // ключ — id кнопки
  return (
    <div className="space-y-2 text-sm">
      {frequent.length > 0 && (
        <p className="rounded bg-amber-50 p-2">За 7 дней чаще всего: {frequent.map(([id, n]) => `«${labels[id] ?? id}» — ${n}`).join("; ")}</p>
      )}
      <ul className="divide-y rounded border bg-white">
        {history.items.slice(0, 30).map((i) => (
          <li key={i.interaction_id} className="flex flex-wrap gap-2 p-2">
            <span className="text-slate-500">{formatDateTime(i.created_at)}</span>
            <span className="flex-1">{i.label}</span>
            <span className="text-xs text-slate-500">{i.sources.map((s) => SOURCE[s] ?? s).join(", ")}</span>
            {i.helped === true && <span className="text-xs text-emerald-700">помогло</span>}
            {i.helped === false && <span className="text-xs text-amber-700">не помогло</span>}
            {i.escalated_message_id && <span className="text-xs text-blue-700">передано врачу</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

const STRESS_TONE: Record<number, string> = { 2: "bg-red-50 text-red-900", 1: "bg-amber-50 text-amber-900" };

/** Внешние факторы стресса: отмеченные — сверху («сильно» → «немного»), остальные свёрнуты. */
export function StressFactors({ patientId }: { patientId: string }) {
  const [view, setView] = useState<StressView | null | undefined>(undefined);
  useEffect(() => {
    api<StressView | null>(`doctor/patients/${patientId}/stress-factors`).then(setView).catch(() => setView(null));
  }, [patientId]);

  if (view === undefined) return null;
  if (view === null) return <p className="text-sm text-slate-500">Пациент ещё не отвечал — опросник откроется у него при первом входе.</p>;
  const present = view.answers.filter((a) => (a.value ?? 0) > 0);
  const rest = view.answers.filter((a) => !a.value);
  return (
    <div className="space-y-2 rounded border bg-white p-3 text-sm">
      <p className="text-slate-600">
        {formatDateTime(view.submitted_at)} · отмечено {view.present_count}, из них сильно влияет — {view.strong_count}.
        Это не шкала: баллов и порогов нет.
      </p>
      {present.length === 0 && <p>Пациент не отметил внешних факторов стресса.</p>}
      <ul className="space-y-1">
        {present.map((a) => (
          <li key={a.id} className={`flex flex-wrap gap-2 rounded px-2 py-1 ${STRESS_TONE[a.value ?? 0]}`}>
            <span className="flex-1">{a.text}</span>
            <span className="text-xs">{a.group}{a.icd && ` · ${a.icd}`}</span>
            <b className="text-xs">{a.value === 2 ? "сильно" : "немного"}</b>
          </li>
        ))}
      </ul>
      {view.other_text && <p><b>Сам(а) добавил(а):</b> {view.other_text}</p>}
      {rest.length > 0 && (
        <details>
          <summary className="cursor-pointer text-slate-500">Не отмечено ({rest.length})</summary>
          <ul className="ml-4 list-disc text-slate-600">
            {rest.map((a) => <li key={a.id}>{a.text} — {a.label.toLowerCase()}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
