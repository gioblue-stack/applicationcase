"use client";
// Карточка пациента (§1.1–§1.3): сводка, флаги, графики, опросники, приверженность, побочные эффекты,
// уточняющий блок, план безопасности. Каждый запрос врача пишется в журнал доступа на сервере.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { DiaryCharts } from "@/components/DiaryCharts";
import { Header } from "@/components/Header";
import { ScoresChart } from "@/components/ScoresChart";
import { coveragePercent } from "@/lib/charts";
import { api } from "@/lib/client";
import {
  COLOR_DOT, COLOR_LABEL, DOSE_STATUS, FLAG_REASON, RISK_LEVEL, formatDate, formatDateTime,
} from "@/lib/labels";
import type {
  DiaryChart, InstrumentHistory, PatientCard, Period, PrescriptionAdherence, RiskAssessmentView, SafetyPlanView,
  SideEffectEntry,
} from "@/lib/types";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

const PERIODS: { value: Period; label: string }[] = [
  { value: "week", label: "Неделя" }, { value: "month", label: "Месяц" }, { value: "all", label: "Весь период" },
];

export default function PatientCardPage() {
  const { id } = useParams<{ id: string }>();
  const base = `doctor/patients/${id}`;
  const [card, setCard] = useState<PatientCard | null>(null);
  const [period, setPeriod] = useState<Period>("month");
  const [diary, setDiary] = useState<DiaryChart | null>(null);
  const [scores, setScores] = useState<InstrumentHistory[]>([]);
  const [adherence, setAdherence] = useState<PrescriptionAdherence[]>([]);
  const [sideEffects, setSideEffects] = useState<SideEffectEntry[]>([]);
  const [risk, setRisk] = useState<RiskAssessmentView[]>([]);
  const [plan, setPlan] = useState<SafetyPlanView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [c, q, a, s, r, p] = await Promise.all([
        api<PatientCard>(`${base}/card`), api<InstrumentHistory[]>(`${base}/questionnaires`),
        api<PrescriptionAdherence[]>(`${base}/adherence`), api<SideEffectEntry[]>(`${base}/side-effects`),
        api<RiskAssessmentView[]>(`${base}/risk-assessments`), api<SafetyPlanView | null>(`${base}/safety-plan`),
      ]);
      setCard(c); setScores(q); setAdherence(a); setSideEffects(s); setRisk(r); setPlan(p);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [base]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api<DiaryChart>(`${base}/diary?period=${period}`).then(setDiary).catch((e) => setError(e.message));
  }, [base, period]);

  async function act(path: string, body?: unknown) {
    try {
      await api(path, { method: "POST", body: body ?? {} });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!card) {
    return (
      <>
        <Header />
        <main className="p-6">{error ? <p role="alert" className="text-red-700">{error}</p> : "Загрузка…"}</main>
      </>
    );
  }

  return (
    <>
      <Header />
      <main className="mx-auto max-w-6xl space-y-8 p-6">
        {error && <p role="alert" className="rounded bg-red-50 p-3 text-red-700">{error}</p>}

        <header className="flex flex-wrap items-start gap-4 rounded-lg bg-white p-4 shadow">
          <span className={`mt-2 h-4 w-4 rounded-full ${COLOR_DOT[card.color]}`} title={COLOR_LABEL[card.color]} />
          <div className="flex-1 space-y-1">
            <h1 className="text-2xl font-semibold">{card.full_name}</h1>
            <p className="text-sm text-slate-600">
              {card.age != null && `${card.age} лет · `}
              {card.diagnoses.map((d) => `${d.code} — ${d.title}`).join("; ") || "Диагноз не указан"}
              {!card.connected && " · ещё не вошёл по приглашению"}
            </p>
            <p className="text-sm">
              {card.latest_scores.map((s) => (
                <span key={s.instrument} className="mr-4">
                  {s.instrument === "PHQ9" ? "PHQ-9" : "GAD-7"}: <b>{s.total}</b> ({s.severity})
                  {s.change != null && <span className={s.significant_change ? "font-semibold" : ""}>
                    {" "}{s.change > 0 ? `+${s.change}` : s.change}</span>}
                </span>
              ))}
              {card.adherence_week_percent != null && <span>Приём за неделю: <b>{card.adherence_week_percent}%</b></span>}
            </p>
          </div>
        </header>

        <Section title="Флаги">
          {card.open_flags.length === 0 && <p className="text-sm text-slate-500">Открытых флагов нет.</p>}
          {card.open_flags.map((f) => (
            <div key={f.flag_id} className="flex items-center gap-3 rounded border bg-white p-3">
              <span className={`h-3 w-3 rounded-full ${COLOR_DOT[f.level]}`} />
              <span className="flex-1">{FLAG_REASON[f.reason] ?? f.reason}
                <span className="ml-2 text-xs text-slate-500">{formatDateTime(f.created_at)}</span></span>
              <button className="rounded bg-slate-800 px-3 py-1 text-sm text-white"
                      onClick={() => act(`doctor/flags/${f.flag_id}/acknowledge`)}>Взять в работу</button>
            </div>
          ))}
        </Section>

        <Section title="Лечение">
          {card.treatment.length === 0 && <p className="text-sm text-slate-500">Схема лечения не внесена.</p>}
          {card.treatment.map((t) => (
            <div key={t.prescription_id} className="rounded border bg-white p-3 text-sm">
              <b>{t.inn}</b>{t.trade_name && ` (${t.trade_name})`} — {t.current_dose} {t.unit}, {t.times.join(", ")}
              {t.upcoming.length > 0 && <div className="text-slate-600">Дальше: {t.upcoming.join("; ")}</div>}
              {card.titration_attention.includes(t.prescription_id) && (
                <ShiftTitration onShift={(days, reason) =>
                  act(`doctor/prescriptions/${t.prescription_id}/shift`, { days, reason })} />
              )}
            </div>
          ))}
          {card.other_medications.length > 0 && (
            <p className="text-sm">Другие препараты: {card.other_medications.map((m) => m.name).join(", ")}</p>
          )}
        </Section>

        <Section title="Дневник">
          <div className="flex flex-wrap items-center gap-2">
            {PERIODS.map((p) => (
              <button key={p.value} onClick={() => setPeriod(p.value)} aria-pressed={period === p.value}
                      className={`rounded px-3 py-1 text-sm ${period === p.value ? "bg-slate-800 text-white" : "border bg-white"}`}>
                {p.label}
              </button>
            ))}
            {diary && <span className="text-sm text-slate-500">
              Заполнено {diary.series.filled_days} из {diary.series.days.length} дней ({coveragePercent(diary.series)}%)
            </span>}
          </div>
          {diary && <DiaryCharts chart={diary} />}
        </Section>

        <Section title="PHQ-9 и GAD-7">
          <ScoresChart histories={scores} />
          {scores.map((h) => (
            <div key={h.instrument} className="rounded border bg-white p-3">
              <h3 className="mb-2 font-medium">{h.title}</h3>
              {[...h.points].reverse().map((p) => (
                <details key={p.submission_id} className="border-t py-1 text-sm">
                  <summary className="cursor-pointer">
                    {formatDate(p.submitted_at)} — <b>{p.total}</b> ({p.severity})
                    {p.change != null && ` ${p.change > 0 ? "+" : ""}${p.change}`}
                    {p.significant_change && " · клинически значимо"}
                    {p.safety_item_positive && " · 9-й вопрос ≠ «Ни разу»"}
                    {p.superseded_by && " · заменено повторным заполнением"}
                  </summary>
                  <ol className="ml-4 list-decimal">
                    {p.answers.map((a) => <li key={a.no}>{a.text}: <b>{a.label}</b></li>)}
                  </ol>
                </details>
              ))}
            </div>
          ))}
        </Section>

        <Section title="Приверженность">
          {adherence.map((row) => (
            <div key={row.prescription_id} className="rounded border bg-white p-3 text-sm">
              <b>{row.inn}</b>{!row.active && " (отменён)"} — неделя: {row.week.taken_percent ?? "—"}%
              ({row.week.taken + row.week.taken_late} из {row.week.due}), месяц: {row.month.taken_percent ?? "—"}%
              {row.week.no_response > 0 && `, без ответа: ${row.week.no_response}`}
              <ul className="mt-1 text-slate-600">
                {row.issues.map((i) => (
                  <li key={i.dose_event_id}>{formatDateTime(i.scheduled_at)} — {DOSE_STATUS[i.status] ?? i.status}
                    {i.actual_dose != null && ` (${i.actual_dose})`}</li>
                ))}
              </ul>
            </div>
          ))}
        </Section>

        <Section title="Побочные эффекты">
          {sideEffects.length === 0 && <p className="text-sm text-slate-500">Записей нет.</p>}
          <ul className="space-y-1 text-sm">
            {sideEffects.map((s) => (
              <li key={s.id}>{formatDate(s.reported_at)} — {s.label}{s.other_text && `: ${s.other_text}`}
                {s.is_new && " · новый"}{s.alarming && ` · тревожный: ${s.doctor_meaning}`}</li>
            ))}
          </ul>
        </Section>

        <Section title="Уточняющий блок">
          {risk.length === 0 && <p className="text-sm text-slate-500">Не проводился.</p>}
          {risk.map((r) => (
            <div key={r.id} className="rounded border bg-white p-3 text-sm">
              {formatDateTime(r.submitted_at)} — уровень <b>{RISK_LEVEL[r.final_level]}</b>
              {r.escalated_by_risk_factors && " (повышен из-за факторов риска)"}
              {r.outcome === "dismissed" && " · закрыт без ответа"}
              <ul className="ml-4 list-disc">
                {r.answers.map((a) => <li key={a.id}>{a.text} — <b>{a.answer == null ? "—" : a.answer ? "Да" : "Нет"}</b></li>)}
              </ul>
            </div>
          ))}
        </Section>

        <Section title="План безопасности">
          {!plan && <p className="text-sm text-slate-500">Пациент ещё не заполнил план.</p>}
          {plan && (
            <div className="space-y-1 rounded border bg-white p-3 text-sm">
              <p className="text-slate-500">Версия {plan.version} от {formatDateTime(plan.updated_at)}</p>
              {plan.warning_signs && <p><b>Сигналы:</b> {plan.warning_signs}</p>}
              {plan.coping_strategies && <p><b>Что помогает:</b> {plan.coping_strategies}</p>}
              {plan.contacts.length > 0 && <p><b>Кому позвонить:</b> {plan.contacts.map((c) => String(c.name)).join(", ")}</p>}
              {plan.means_restriction && <p><b>Ограничение доступа к средствам:</b> {plan.means_restriction}</p>}
              {plan.doctor_reviewed_at
                ? <p className="text-slate-500">Просмотрено {formatDateTime(plan.doctor_reviewed_at)}</p>
                : <button className="rounded bg-slate-800 px-3 py-1 text-white"
                          onClick={() => act(`${base}/safety-plan/review`)}>Отметить просмотренным</button>}
            </div>
          )}
        </Section>
      </main>
    </>
  );
}

function ShiftTitration({ onShift }: { onShift: (days: number, reason: string) => void }) {
  const [days, setDays] = useState(7);
  return (
    <form className="mt-2 flex flex-wrap items-center gap-2 rounded bg-amber-50 p-2"
          onSubmit={(e) => { e.preventDefault(); onShift(days, "Пропуски на текущем этапе"); }}>
      <span>Пропуск пришёлся на этап перед повышением дозы.</span>
      <label>Сдвинуть следующие этапы на
        <input type="number" min={1} max={60} value={days} onChange={(e) => setDays(Number(e.target.value))}
               className="mx-1 w-16 rounded border px-1" /> дн.</label>
      <button className="rounded bg-slate-800 px-2 py-1 text-white">Сдвинуть</button>
    </form>
  );
}
