"use client";
// Назначение препарата (§1.2, §1.3): препарат из демо-базы, доза, время приёма, правило при пропуске, титрация.
// Схема вносится после очного приёма: дата начала не раньше даты приёма — это проверяет и сервер.
import { useEffect, useState } from "react";
import { api } from "@/lib/client";

type MissedRule = "take_if_more_than_hours" | "skip_no_double" | "contact_doctor";

type Drug = {
  id: string;
  inn: string;
  trade_names: string[];
  group_label: string | null;
  default_missed_dose_rule: MissedRule | null;
  default_missed_dose_hours: number | null;
};

const MISSED_RULES: { value: MissedRule; label: string }[] = [
  { value: "take_if_more_than_hours", label: "Принять, если до следующего приёма больше N часов" },
  { value: "skip_no_double", label: "Пропустить, двойную дозу не принимать" },
  { value: "contact_doctor", label: "Сообщить врачу" },
];

const FOOD = [
  { value: "", label: "Не указано" },
  { value: "before", label: "До еды" },
  { value: "after", label: "После еды" },
  { value: "any", label: "Независимо от еды" },
];

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const input = "w-full rounded border px-2 py-1";

export function PrescribeForm({ patientId, onDone, onCancel }: {
  patientId: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [drugs, setDrugs] = useState<Drug[]>([]);
  const [substance, setSubstance] = useState("");
  const [tradeName, setTradeName] = useState("");
  const [form, setForm] = useState("таблетки");
  const [dose, setDose] = useState("");
  const [unit, setUnit] = useState("мг");
  const [times, setTimes] = useState(["09:00"]);
  const [withFood, setWithFood] = useState("");
  const [instructions, setInstructions] = useState("");
  const [visit, setVisit] = useState(today());
  const [start, setStart] = useState(today());
  const [end, setEnd] = useState("");
  const [rule, setRule] = useState<MissedRule | "">("");
  const [hours, setHours] = useState("");
  const [steps, setSteps] = useState<{ effective_date: string; dose: string }[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Drug[]>("doctor/formulary").then(setDrugs).catch((e) => setError((e as Error).message));
  }, []);

  function pickDrug(id: string) {
    setSubstance(id);
    const drug = drugs.find((d) => d.id === id);
    // Единственное торговое название подставляется само; при смене препарата старое не остаётся.
    setTradeName(drug?.trade_names.length === 1 ? drug.trade_names[0] : "");
    // Правило по умолчанию — из инструкции, если оно сверено; в демо-базе его нет, и врач выбирает сам.
    setRule(drug?.default_missed_dose_rule ?? "");
    setHours(drug?.default_missed_dose_hours ? String(drug.default_missed_dose_hours) : "");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`doctor/patients/${patientId}/prescriptions`, {
        method: "POST",
        body: {
          substance_id: substance, trade_name: tradeName.trim() || null, form: form.trim(),
          dose: dose.replace(",", "."), unit: unit.trim(), times, with_food: withFood || null,
          instructions: instructions.trim() || null, start_date: start, end_date: end || null,
          in_person_visit_date: visit, missed_dose_rule: rule,
          missed_dose_hours: rule === "take_if_more_than_hours" ? Number(hours) : null,
          titration: steps.map((s) => ({ effective_date: s.effective_date, dose: s.dose.replace(",", ".") })),
        },
      });
      onDone();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const drug = drugs.find((d) => d.id === substance);

  return (
    <form onSubmit={submit} className="space-y-3 rounded border bg-white p-4 text-sm">
      <h3 className="text-base font-semibold">Новое назначение</h3>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="font-medium">Препарат (МНН)</span>
          <select required value={substance} onChange={(e) => pickDrug(e.target.value)} className={input}>
            <option value="">— выберите —</option>
            {drugs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.inn}{d.trade_names.length > 0 && ` (${d.trade_names.join(", ")})`}{d.group_label && ` — ${d.group_label}`}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="font-medium">Торговое название <span className="text-slate-500">(необязательно)</span></span>
          <input value={tradeName} onChange={(e) => setTradeName(e.target.value)} list="trade-names" maxLength={200}
                 className={input} />
          <datalist id="trade-names">{drug?.trade_names.map((t) => <option key={t} value={t} />)}</datalist>
        </label>
        <label className="space-y-1">
          <span className="font-medium">Доза на приём</span>
          <span className="flex gap-2">
            <input required value={dose} onChange={(e) => setDose(e.target.value)} inputMode="decimal" placeholder="50"
                   className={input} />
            <input required value={unit} onChange={(e) => setUnit(e.target.value)} maxLength={16}
                   className="w-20 rounded border px-2 py-1" />
          </span>
        </label>
        <label className="space-y-1">
          <span className="font-medium">Форма</span>
          <input required value={form} onChange={(e) => setForm(e.target.value)} maxLength={100} className={input} />
        </label>
      </div>

      <fieldset className="space-y-1">
        <legend className="font-medium">Время приёма</legend>
        <div className="flex flex-wrap items-center gap-2">
          {times.map((t, i) => (
            <span key={i} className="flex items-center gap-1">
              <input type="time" required value={t}
                     onChange={(e) => setTimes(times.map((x, j) => (j === i ? e.target.value : x)))}
                     className="rounded border px-2 py-1" />
              {times.length > 1 && (
                <button type="button" aria-label="Убрать время" onClick={() => setTimes(times.filter((_, j) => j !== i))}
                        className="px-1 text-slate-400">✕</button>
              )}
            </span>
          ))}
          {times.length < 6 && (
            <button type="button" onClick={() => setTimes([...times, "21:00"])} className="text-slate-700 underline">
              + ещё приём
            </button>
          )}
        </div>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1">
          <span className="font-medium">Приём пищи</span>
          <select value={withFood} onChange={(e) => setWithFood(e.target.value)} className={input}>
            {FOOD.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="font-medium">Дата очного приёма</span>
          <input type="date" required value={visit} onChange={(e) => setVisit(e.target.value)} className={input} />
        </label>
        <label className="space-y-1">
          <span className="font-medium">Начать с</span>
          <input type="date" required value={start} min={visit} onChange={(e) => setStart(e.target.value)}
                 className={input} />
        </label>
        <label className="space-y-1">
          <span className="font-medium">Закончить <span className="text-slate-500">(необязательно)</span></span>
          <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} className={input} />
        </label>
      </div>

      <fieldset className="space-y-1">
        <legend className="font-medium">Если пациент пропустил приём</legend>
        {MISSED_RULES.map((r) => (
          <label key={r.value} className="flex flex-wrap items-center gap-2">
            <input type="radio" name="missed" required checked={rule === r.value} onChange={() => setRule(r.value)} />
            {r.label}
            {r.value === "take_if_more_than_hours" && rule === r.value && (
              <span className="flex items-center gap-1">
                — N =
                <input type="number" required min={1} max={24} value={hours} onChange={(e) => setHours(e.target.value)}
                       className="w-16 rounded border px-1" /> ч
              </span>
            )}
          </label>
        ))}
        <p className="text-xs text-slate-500">Это правило пациент увидит сразу, как только отметит пропуск.</p>
      </fieldset>

      <fieldset className="space-y-1">
        <legend className="font-medium">Титрация <span className="text-slate-500">(смена дозы по датам, необязательно)</span></legend>
        {steps.map((s, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            с <input type="date" required value={s.effective_date} min={start}
                     onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { ...x, effective_date: e.target.value } : x)))}
                     className="rounded border px-2 py-1" />
            доза <input required value={s.dose} inputMode="decimal"
                        onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { ...x, dose: e.target.value } : x)))}
                        className="w-20 rounded border px-2 py-1" /> {unit}
            <button type="button" aria-label="Убрать этап" onClick={() => setSteps(steps.filter((_, j) => j !== i))}
                    className="px-1 text-slate-400">✕</button>
          </div>
        ))}
        <button type="button" onClick={() => setSteps([...steps, { effective_date: "", dose: "" }])}
                className="text-slate-700 underline">+ этап</button>
      </fieldset>

      <label className="block space-y-1">
        <span className="font-medium">Указания пациенту <span className="text-slate-500">(необязательно)</span></span>
        <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={2} maxLength={1000}
                  className={input} />
      </label>

      {error && <p role="alert" className="rounded bg-red-50 p-2 text-red-700">{error}</p>}
      <div className="flex gap-2">
        <button disabled={busy} className="rounded bg-slate-800 px-4 py-2 text-white disabled:opacity-50">Назначить</button>
        <button type="button" onClick={onCancel} className="rounded border px-4 py-2">Отмена</button>
      </div>
    </form>
  );
}

/** Изменить дозу с даты или отменить препарат. Оба действия пишутся в историю схемы. */
export function PrescriptionActions({ prescriptionId, unit, onDone, onError }: {
  prescriptionId: string;
  unit: string;
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [mode, setMode] = useState<"" | "dose" | "stop">("");
  const [date, setDate] = useState(today());
  const [dose, setDose] = useState("");
  const [reason, setReason] = useState("");

  async function send(path: string, body: unknown) {
    try {
      await api(`doctor/prescriptions/${prescriptionId}/${path}`, { method: "POST", body });
      setMode("");
      setReason("");
      onDone();
    } catch (e) {
      onError((e as Error).message);
    }
  }

  if (mode === "dose") {
    return (
      <form className="mt-2 flex flex-wrap items-center gap-2 rounded bg-slate-50 p-2"
            onSubmit={(e) => {
              e.preventDefault();
              send("dose-change", { effective_date: date, dose: dose.replace(",", "."), reason: reason || null });
            }}>
        Новая доза <input required value={dose} onChange={(e) => setDose(e.target.value)} inputMode="decimal"
                          className="w-20 rounded border px-2 py-1" /> {unit}
        с <input type="date" required min={today()} value={date} onChange={(e) => setDate(e.target.value)}
                 className="rounded border px-2 py-1" />
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Причина (необязательно)"
               maxLength={500} className="min-w-48 flex-1 rounded border px-2 py-1" />
        <button className="rounded bg-slate-800 px-3 py-1 text-white">Сохранить</button>
        <button type="button" onClick={() => setMode("")} className="rounded border px-3 py-1">Отмена</button>
      </form>
    );
  }

  if (mode === "stop") {
    return (
      <form className="mt-2 flex flex-wrap items-center gap-2 rounded bg-red-50 p-2"
            onSubmit={(e) => { e.preventDefault(); send("stop", { reason: reason || null }); }}>
        <span>Отменить препарат? Будущие приёмы удалятся, пациент увидит изменение в схеме.</span>
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Причина (необязательно)"
               maxLength={500} className="min-w-48 flex-1 rounded border px-2 py-1" />
        <button className="rounded bg-red-700 px-3 py-1 text-white">Отменить препарат</button>
        <button type="button" onClick={() => setMode("")} className="rounded border px-3 py-1">Не отменять</button>
      </form>
    );
  }

  return (
    <div className="mt-2 flex gap-3">
      <button onClick={() => setMode("dose")} className="text-slate-700 underline">Изменить дозу</button>
      <button onClick={() => setMode("stop")} className="text-red-700 underline">Отменить</button>
    </div>
  );
}
