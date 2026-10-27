// Один приём: отметка «Принял(а) / Пропустил(а) / Изменил(а) дозу», отложить, правило врача при пропуске (§1.2, §1.3).
"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/client";
import type { Dose, DoseResult } from "@/lib/types";

const HOUR = 60 * 60_000;

const STATUS: Record<Dose["status"], string> = {
  pending: "",
  taken: "Принято ✓",
  taken_late: "Принято позже ✓",
  missed: "Пропущено",
  self_changed: "Доза изменена",
  no_response: "Нет отметки",
};

export default function DoseRow({ dose, onChange }: { dose: Dose; onChange: () => void }) {
  const [result, setResult] = useState<DoseResult | null>(null);
  const [changing, setChanging] = useState(false);
  const [actual, setActual] = useState("");
  const [error, setError] = useState("");
  const sinceScheduled = Date.now() - new Date(dose.scheduled_at).getTime();
  const late = sinceScheduled > HOUR;
  const tooEarly = sinceScheduled < -HOUR; // сервер принимает отметку не раньше чем за час до приёма

  async function answer(response: string, actual_dose?: string) {
    setError("");
    try {
      const r = await api<DoseResult>(`me/doses/${dose.id}/response`, {
        method: "POST", body: { response, ...(actual_dose ? { actual_dose } : {}) } });
      setResult(r);
      setChanging(false);
      if (!r.guidance && !r.offer_risk_block) onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function snooze(minutes: number) {
    try {
      await api(`me/doses/${dose.id}/snooze`, { method: "POST", body: { minutes } });
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const name = dose.trade_name ? `${dose.inn} (${dose.trade_name})` : dose.inn;
  return (
    <li className="py-3">
      <div className="flex items-baseline justify-between gap-2">
        <p><span className="font-semibold">{dose.local_time}</span> · {name} {dose.dose} {dose.unit}</p>
        <span className="shrink-0 text-sm text-gray-500">{STATUS[result?.status ?? dose.status]}</span>
      </div>

      {dose.answerable && !result && tooEarly && (
        <p className="mt-1 text-xs text-gray-500">Отметить можно за час до приёма.</p>
      )}
      {dose.answerable && !result && !tooEarly && (
        <div className="mt-2 grid grid-cols-2 gap-2">
          <button onClick={() => answer(late ? "taken_late" : "taken")}
                  className="rounded-lg bg-teal-600 py-2 text-sm font-semibold text-white">
            {late ? "Принял(а) позже" : "Принял(а)"}
          </button>
          <button onClick={() => answer("missed")} className="rounded-lg bg-gray-100 py-2 text-sm">Пропустил(а)</button>
          <button onClick={() => setChanging(!changing)} className="rounded-lg bg-gray-100 py-2 text-sm">
            Изменил(а) дозу
          </button>
          {dose.status === "pending" && (
            <button onClick={() => snooze(15)} className="rounded-lg bg-gray-100 py-2 text-sm">Через 15 минут</button>
          )}
        </div>
      )}
      {dose.snoozed_until && dose.status === "pending" && (
        <p className="mt-1 text-xs text-gray-500">
          Напомним в {new Date(dose.snoozed_until).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
        </p>
      )}

      {changing && (
        <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); answer("self_changed", actual.replace(",", ".")); }}>
          <input value={actual} onChange={(e) => setActual(e.target.value)} inputMode="decimal" required
                 placeholder={`Сколько ${dose.unit} приняли`} className="flex-1 rounded-lg border border-gray-300 px-3 py-2" />
          <button className="rounded-lg bg-teal-600 px-4 text-sm font-semibold text-white">Отметить</button>
        </form>
      )}

      {result?.guidance && (
        <div className="mt-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-950">
          <p>{result.guidance.rule_text}</p>
          {result.guidance.hint_text && <p className="mt-1 font-semibold">{result.guidance.hint_text}</p>}
          <p className="mt-1 text-xs text-amber-800">{result.guidance.author_note}</p>
        </div>
      )}
      {result?.offer_risk_block && (
        <Link href={`/risk?trigger=${result.offer_risk_block}`}
              className="mt-2 block rounded-lg bg-teal-50 p-3 text-sm text-teal-900 ring-1 ring-teal-200">
          Ответьте, пожалуйста, на несколько вопросов о самочувствии →
        </Link>
      )}
      {error && <p className="mt-2 text-sm text-amber-800">{error}</p>}
    </li>
  );
}
