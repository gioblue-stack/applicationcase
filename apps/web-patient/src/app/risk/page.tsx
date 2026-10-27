// Уточняющий блок при суицидальном риске (§4.6, §7.1). Уровень определяет сервер; «Не сейчас» и закрытие
// на середине тоже отправляются — врач получит сигнал в любом случае.
"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import HelpView from "@/components/HelpView";
import Shell, { Card, ErrorText } from "@/components/Shell";
import { api, newId, nowIso } from "@/lib/client";
import { useContent } from "@/lib/content";
import { localScreen, visibleRiskQuestions } from "@/lib/help";
import { helpProfile, type HelpProfile } from "@/lib/local";
import type { HelpScreen } from "@/lib/types";

type Result = { final_level: string; screen: HelpScreen };

export default function RiskPage() {
  const content = useContent();
  const [params, setParams] = useState<{ trigger: string; ref: string | null } | null>(null);
  const [profile, setProfile] = useState<HelpProfile | null>(null);
  const [started, setStarted] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [screen, setScreen] = useState<HelpScreen | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [locked, setLocked] = useState(false);
  const order = useRef<string[]>([]); // порядок ответов — для кнопки «Назад»
  const clientId = useRef(newId());

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setParams({ trigger: q.get("trigger") ?? "", ref: q.get("ref") });
    setProfile(helpProfile());
  }, []);

  if (!content || !params || !profile) return <Shell title="Несколько вопросов">{null}</Shell>;
  const block = content.suicide_block;
  const visible = visibleRiskQuestions(block.questions, answers);
  const current = visible.find((q) => answers[q.id] === undefined);

  async function send(final: Record<string, boolean>) {
    setBusy(true);
    setError("");
    try {
      const r = await api<Result>("me/risk-assessments", {
        method: "POST",
        body: {
          client_id: clientId.current, trigger: params!.trigger, trigger_ref: params!.ref, answers: final,
          started_at: started, client_submitted_at: nowIso(),
        },
      });
      setScreen(r.screen);
      setError("");
    } catch (e) {
      // Ответ сервера не пришёл — телефоны помощи всё равно на экране.
      setScreen(localScreen(content!, "help", profile!.region));
      setError(`Ответы не отправились: ${(e as Error).message}. Попробуйте ещё раз, когда будет связь.`);
    } finally {
      setBusy(false);
    }
  }

  function answer(id: string, value: boolean) {
    if (locked) return;
    // Следующий вопрос появляется на месте кнопок: пауза, чтобы двойное касание не ответило и на него.
    setLocked(true);
    setTimeout(() => setLocked(false), 600);
    const updated = { ...answers, [id]: value };
    // Ответ «нет» на q2 убирает уточняющие q3–q5, если они уже были отвечены.
    const shown = new Set(visibleRiskQuestions(block.questions, updated).map((q) => q.id));
    const kept = Object.fromEntries(Object.entries(updated).filter(([q]) => shown.has(q)));
    order.current = [...order.current.filter((q) => q in kept && q !== id), id];
    setAnswers(kept);
    if (visibleRiskQuestions(block.questions, kept).every((q) => kept[q.id] !== undefined)) send(kept);
  }

  function back() {
    const last = order.current.pop();
    if (!last) return;
    const rest = { ...answers };
    delete rest[last];
    setAnswers(rest);
  }

  if (screen) {
    return (
      <Shell title="Помощь">
        <div className="mt-4"><HelpView screen={screen} contacts={profile.contacts} /></div>
        <ErrorText>{error}</ErrorText>
        {error && (
          <button onClick={() => send(answers)} disabled={busy}
                  className="mt-3 w-full rounded-xl bg-brand-600 btn-3d py-3 font-semibold text-white">Отправить ещё раз</button>
        )}
        <Link href="/" className="mt-4 block text-center text-brand-700">На главную</Link>
      </Shell>
    );
  }

  if (!started) {
    const phones = localScreen(content, "help", profile.region);
    return (
      <Shell title="Несколько вопросов">
        <Card>
          <p className="text-lg leading-relaxed">{block.intro.text}</p>
          <button onClick={() => setStarted(nowIso())}
                  className="mt-4 w-full rounded-xl bg-brand-600 btn-3d py-3 font-semibold text-white">{block.intro.buttons.answer}</button>
          <button onClick={() => send({})} disabled={busy}
                  className="mt-2 w-full rounded-xl bg-gray-100 py-3">{block.intro.buttons.dismiss}</button>
        </Card>
        <Card>
          <p className="text-sm font-semibold text-gray-500">Если тяжело прямо сейчас</p>
          {phones.phones.map((p) => (
            <a key={p.id} href={`tel:${p.tel}`} className="mt-2 block text-brand-800">
              <span className="font-semibold">{p.display}</span> — {p.service}
            </a>
          ))}
        </Card>
      </Shell>
    );
  }

  return (
    <Shell title="Несколько вопросов">
      {current && (
        <Card>
          <p className="text-sm text-gray-500">Вопрос {visible.indexOf(current) + 1} из {visible.length}</p>
          <p className="mt-2 text-lg leading-relaxed">{current.text}</p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {block.answer_options.map((o) => (
              <button key={String(o.value)} onClick={() => answer(current.id, o.value)} disabled={busy || locked}
                      className="rounded-xl bg-brand-600 btn-3d py-4 text-lg font-semibold text-white disabled:opacity-60">
                {o.label}
              </button>
            ))}
          </div>
          {order.current.length > 0 && (
            <button onClick={back} disabled={busy} className="mt-4 text-sm text-brand-700">‹ Назад</button>
          )}
        </Card>
      )}
      {/* Закрыть на середине — частичный ответ: сервер ставит не ниже красного (В3). */}
      <button onClick={() => send(answers)} disabled={busy} className="mt-4 w-full text-center text-gray-500">
        Закрыть
      </button>
    </Shell>
  );
}
