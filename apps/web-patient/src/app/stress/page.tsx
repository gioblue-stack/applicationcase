// «Что сейчас происходит в жизни»: внешние факторы стресса при первом входе (обновить — из «Профиля»).
// Это не шкала: баллов нет, ответы видит лечащий врач. На любой вопрос можно не отвечать.
"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import HelpView from "@/components/HelpView";
import { MascotSays } from "@/components/Mascot";
import Shell, { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { api, newId } from "@/lib/client";
import { useContent } from "@/lib/content";
import type { StressResult } from "@/lib/types";

export default function StressPage() {
  const content = useContent();
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [other, setOther] = useState("");
  const [result, setResult] = useState<StressResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const clientId = useRef(newId());

  const stress = content?.instruments.STRESS;
  if (!stress) return <Shell title="О жизненной ситуации" back>{null}</Shell>;
  const answered = Object.keys(answers).length > 0 || other.trim().length > 0;

  async function submit() {
    setBusy(true);
    setError("");
    try {
      setResult(await api<StressResult>("me/stress-factors", {
        method: "POST", body: { client_id: clientId.current, answers, other_text: other.trim() || null },
      }));
      window.scrollTo({ top: 0 });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <Shell title={stress.title} back>
        {result.help_screen && <div className="mt-4"><HelpView screen={result.help_screen} /></div>}
        {result.safety_text && (
          <Card className="bg-red-50 ring-1 ring-red-200">
            <p>{result.safety_text}</p>
            <a href="tel:112" className="mt-3 block rounded-2xl bg-help btn-solid-red py-3 text-center font-semibold text-white">
              Позвонить 112
            </a>
          </Card>
        )}
        {!result.help_screen && <MascotSays pose="both-wings">{stress.outro}</MascotSays>}
        <Link href="/" className="mt-4 block rounded-2xl bg-brand-600 btn-solid py-3 text-center font-semibold text-white">
          На главную
        </Link>
      </Shell>
    );
  }

  return (
    <Shell title={stress.title} back>
      <MascotSays pose="standing">{stress.intro}</MascotSays>
      {Object.entries(stress.groups).map(([group, title]) => (
        <div key={group}>
          <p className="mt-6 text-lg font-bold text-brand-900">{title}</p>
          {stress.items.filter((i) => i.group === group).map((item) => (
            <Card key={item.id}>
              <p className="mb-3">{item.text}</p>
              <div className="grid grid-cols-3 gap-2">
                {stress.options.map((o) => (
                  <button key={o.value} type="button"
                          onClick={() => setAnswers({ ...answers, [item.id]: o.value })}
                          className={`rounded-2xl px-2 py-2 text-xs ${answers[item.id] === o.value ? "bg-brand-600 btn-solid font-semibold text-white" : "bg-subtle"}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </Card>
          ))}
        </div>
      ))}
      <Card>
        <p className="mb-2">{stress.other_prompt}</p>
        <textarea value={other} onChange={(e) => setOther(e.target.value)} rows={3} maxLength={500}
                  className="w-full rounded-2xl border border-line p-2" />
      </Card>
      <ErrorText>{error}</ErrorText>
      <PrimaryButton onClick={submit} disabled={busy || !answered} className="mt-4">
        {answered ? "Отправить врачу" : "Ответьте хотя бы на один вопрос"}
      </PrimaryButton>
      <Link href="/" className="mt-3 block py-2 text-center text-sm text-muted">Заполню позже</Link>
    </Shell>
  );
}
