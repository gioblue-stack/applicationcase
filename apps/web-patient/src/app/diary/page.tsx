// Ежедневный дневник (§4.3). Можно ответить не на все вопросы; пропуск хранится как «нет ответа», а не 0.
"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import HelpView from "@/components/HelpView";
import Mascot from "@/components/Mascot";
import Scale from "@/components/Scale";
import Shell, { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { api, newId, nowIso } from "@/lib/client";
import { useContent } from "@/lib/content";
import type { HelpScreen, Me, Today } from "@/lib/types";

type Result = { help_screen: HelpScreen | null; offer_risk_block: string | null };

export default function DiaryPage() {
  const content = useContent();
  const [me, setMe] = useState<Me | null>(null);
  const [today, setToday] = useState<Today | null>(null);
  const [values, setValues] = useState<Record<string, number | null>>({});
  const [sleepHours, setSleepHours] = useState<number | null>(null);
  const [meds, setMeds] = useState<string | null>(null);
  const [hadEffects, setHadEffects] = useState<boolean | null>(null);
  const [effects, setEffects] = useState<string[]>([]);
  const [otherText, setOtherText] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const clientId = useRef(newId()); // повторная отправка той же формы не создаёт вторую запись

  useEffect(() => {
    (async () => {
      const [profile, day] = await Promise.all([api<Me>("me"), api<Today>("me/today")]);
      setMe(profile);
      setToday(day);
      if (profile.takes_medication) {
        // Вопрос 7 заполняется из отметок о приёме; пациент может поправить (§4.3).
        const hint = await api<{ meds_taken: string | null }>(`me/diary/meds-suggestion?day=${day.day}`);
        setMeds(hint.meds_taken);
      }
    })().catch((e) => setError((e as Error).message));
  }, []);

  if (!content || !me || !today) return <Shell title="Дневник" back><ErrorText>{error}</ErrorText></Shell>;
  const diary = content.instruments.DIARY;
  const questions = diary.questions.filter((q) => !q.medication_only || me.takes_medication);
  const set = (id: string) => (v: number | null) => setValues({ ...values, [id]: v });

  async function submit() {
    setBusy(true);
    setError("");
    const sideEffects = hadEffects
      ? effects.map((code) => (code === "other" ? { code, other_text: otherText.trim() } : { code }))
      : [];
    try {
      const r = await api<Result>("me/diary", {
        method: "POST",
        body: {
          client_id: clientId.current, day: today!.day, client_submitted_at: nowIso(),
          supersedes_id: today!.diary_entry_id,
          mood: values.mood ?? null, interest: values.interest ?? null, anxiety: values.anxiety ?? null,
          worry_control: values.worry_control ?? null, energy: values.energy ?? null,
          sleep_hours: sleepHours, sleep_quality: values.sleep_quality ?? null,
          ...(me!.takes_medication ? { meds_taken: meds, had_side_effects: hadEffects, side_effects: sideEffects } : {}),
        },
      });
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <Shell title="Дневник" back>
        {result.help_screen ? (
          <div className="mt-4"><HelpView screen={result.help_screen} /></div>
        ) : (
          <div className="mt-6 flex flex-col items-center text-center">
            <Mascot pose="both-wings" size={160} />
            <p className="mt-3 text-2xl font-extrabold text-brand-800">Записали!</p>
            <p className="mt-1 font-semibold text-brand-900/70">Врач увидит, как меняется самочувствие день ото дня.</p>
          </div>
        )}
        {result.offer_risk_block && (
          <Card className="ring-1 ring-amber-300">
            <p>Ответьте, пожалуйста, на несколько коротких вопросов о самочувствии.</p>
            <Link href={`/risk?trigger=${result.offer_risk_block}`}
                  className="mt-3 block rounded-xl bg-brand-600 btn-3d py-3 text-center font-semibold text-white">Ответить</Link>
          </Card>
        )}
        <Link href="/" className="mt-4 block text-center text-brand-700">На главную</Link>
      </Shell>
    );
  }

  return (
    <Shell title="Дневник" back>
      <p className="mt-2 text-gray-600">{diary.invitation} Можно пропустить любой вопрос.</p>
      {questions.map((q) => (
        <Card key={q.id}>
          <p className="mb-3 font-medium">{q.text}</p>
          {q.type === "scale" && (
            <Scale value={values[q.id] ?? null} onChange={set(q.id)} minLabel={q.min_label} maxLabel={q.max_label} />
          )}
          {q.type === "sleep" && (
            <>
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-600">Часов сна</span>
                <button type="button" onClick={() => setSleepHours(Math.max(0, (sleepHours ?? 7.5) - 0.5))}
                        className="size-10 rounded-full bg-gray-100 text-xl">−</button>
                <span className="w-14 text-center text-lg font-semibold">{sleepHours ?? "—"}</span>
                <button type="button" onClick={() => setSleepHours(Math.min(24, (sleepHours ?? 6.5) + 0.5))}
                        className="size-10 rounded-full bg-gray-100 text-xl">+</button>
                {sleepHours !== null && (
                  <button type="button" onClick={() => setSleepHours(null)} className="text-sm text-gray-500">сбросить</button>
                )}
              </div>
              <p className="mb-2 mt-4 text-sm text-gray-600">Качество сна</p>
              <Scale value={values.sleep_quality ?? null} onChange={set("sleep_quality")}
                     minLabel={q.quality_min_label} maxLabel={q.quality_max_label} />
            </>
          )}
          {q.type === "meds" && (
            <div className="flex flex-col gap-2">
              {q.options!.map((o) => (
                <button key={o.value} type="button" onClick={() => setMeds(meds === o.value ? null : o.value)}
                        className={`rounded-lg py-2 ${meds === o.value ? "bg-brand-600 btn-3d font-semibold text-white" : "bg-gray-100"}`}>
                  {o.label}
                </button>
              ))}
            </div>
          )}
          {q.type === "side_effects" && (
            <>
              <div className="grid grid-cols-2 gap-2">
                {[true, false].map((v) => (
                  <button key={String(v)} type="button" onClick={() => setHadEffects(hadEffects === v ? null : v)}
                          className={`rounded-lg py-2 ${hadEffects === v ? "bg-brand-600 btn-3d font-semibold text-white" : "bg-gray-100"}`}>
                    {v ? "Да" : "Нет"}
                  </button>
                ))}
              </div>
              {hadEffects && (
                <div className="mt-3 flex flex-col gap-2">
                  {diary.side_effect_options.map((o) => (
                    <label key={o.code} className="flex items-center gap-3">
                      <input type="checkbox" className="size-5" checked={effects.includes(o.code)}
                             onChange={(e) => setEffects(e.target.checked ? [...effects, o.code] : effects.filter((c) => c !== o.code))} />
                      {o.label}
                    </label>
                  ))}
                  {effects.includes("other") && (
                    <textarea value={otherText} onChange={(e) => setOtherText(e.target.value)} maxLength={500} rows={2}
                              placeholder="Что именно беспокоит" className="rounded-lg border border-gray-300 p-2" />
                  )}
                </div>
              )}
            </>
          )}
        </Card>
      ))}
      <ErrorText>{error}</ErrorText>
      <PrimaryButton onClick={submit} disabled={busy} className="mt-4">Сохранить</PrimaryButton>
    </Shell>
  );
}
