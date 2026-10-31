// Самопроверка для пользователя без врача (§3.1): PHQ-9 и GAD-7 подряд, итог простым языком, «это не диагноз».
// 9-й вопрос PHQ-9 не «Ни разу» — экран помощи независимо от суммы.
"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import HelpView from "@/components/HelpView";
import { MascotSays } from "@/components/Mascot";
import Shell, { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { ApiError, api, newId, nowIso } from "@/lib/client";
import { useContent } from "@/lib/content";
import type { Instrument, SelfCheckResult } from "@/lib/types";

const ACTION_TEXT: Record<string, string> = {
  repeat_in_14_days: "Повторить самопроверку можно через 2 недели.",
  find_specialist: "Записаться к психиатру или психотерапевту можно в поликлинике по месту жительства или в частной клинике.",
};

function Questions({ instrument, answers, onAnswer }: {
  instrument: Instrument; answers: (number | null)[]; onAnswer: (i: number, v: number) => void;
}) {
  return (
    <>
      <p className="mt-6 text-lg font-bold text-brand-900">{instrument.title}</p>
      <p className="mt-1 font-medium">{instrument.instruction}</p>
      {instrument.items.map((item, i) => (
        <Card key={item.no}>
          <p className="mb-3">{item.no}. {item.text}</p>
          <div className="grid grid-cols-2 gap-2">
            {instrument.options.map((o) => (
              <button key={o.value} type="button" onClick={() => onAnswer(i, o.value)}
                      className={`rounded-lg px-2 py-2 text-sm ${answers[i] === o.value ? "bg-brand-600 btn-3d font-semibold text-white" : "bg-gray-100"}`}>
                {o.label}
              </button>
            ))}
          </div>
        </Card>
      ))}
    </>
  );
}

export default function SelfCheckPage() {
  const content = useContent();
  const [phq9, setPhq9] = useState<(number | null)[]>([]);
  const [gad7, setGad7] = useState<(number | null)[]>([]);
  const [result, setResult] = useState<SelfCheckResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const ids = useRef({ phq9: newId(), gad7: newId() });

  if (!content) return <Shell title="Самопроверка" back>{null}</Shell>;
  const { PHQ9, GAD7 } = content.instruments;
  const complete = PHQ9.items.every((_, i) => phq9[i] != null) && GAD7.items.every((_, i) => gad7[i] != null);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      setResult(await api<SelfCheckResult>("me/self-check", {
        method: "POST",
        body: { phq9_client_id: ids.current.phq9, gad7_client_id: ids.current.gad7, phq9_answers: phq9,
                gad7_answers: gad7, client_submitted_at: nowIso() },
      }));
      window.scrollTo({ top: 0 });
    } catch (e) {
      const at = e instanceof ApiError ? (e.data as { available_at?: string } | null)?.available_at : undefined;
      setError(at ? `Повторить самопроверку можно с ${new Date(at).toLocaleDateString("ru-RU")}.` : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <Shell title="Самопроверка" back>
        {result.help_screen && <div className="mt-4"><HelpView screen={result.help_screen} /></div>}
        <Card>
          <p className="text-lg">{result.text}</p>
          {result.actions.filter((a) => ACTION_TEXT[a]).map((a) => <p key={a} className="mt-2">{ACTION_TEXT[a]}</p>)}
          <p className="mt-3 text-sm text-gray-500">{result.screening_note}</p>
        </Card>
        <Link href="/" className="mt-4 block text-center text-brand-700">На главную</Link>
      </Shell>
    );
  }

  const set = (list: (number | null)[], update: (v: (number | null)[]) => void) => (i: number, v: number) =>
    update(Object.assign([...list], { [i]: v }));
  return (
    <Shell title="Самопроверка" back>
      <MascotSays pose="standing">Два коротких опросника — около 5 минут. Это скрининг, а не диагноз.</MascotSays>
      <Questions instrument={PHQ9} answers={phq9} onAnswer={set(phq9, setPhq9)} />
      <Questions instrument={GAD7} answers={gad7} onAnswer={set(gad7, setGad7)} />
      <ErrorText>{error}</ErrorText>
      <PrimaryButton onClick={submit} disabled={busy || !complete} className="mt-4">
        {complete ? "Узнать результат" : "Ответьте на все вопросы"}
      </PrimaryButton>
      {PHQ9.copyright && <p className="mt-4 text-xs text-gray-400">{PHQ9.copyright}</p>}
    </Shell>
  );
}
