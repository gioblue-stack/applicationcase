// Ассистент (§2.3, §5.4): готовые вопросы, у каждого ответа виден источник. Ничего не сочиняет,
// лечение менять не советует; опасное или неизвестное — сразу врачу.
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import HelpView from "@/components/HelpView";
import { MascotSays } from "@/components/Mascot";
import Shell, { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { api, newId, upload } from "@/lib/client";
import type { AlarmingResult, AssistantAnswer, AssistantTree, Me, Substance } from "@/lib/types";

const SOURCE: Record<string, string> = {
  "Д": "Ваши данные", "И": "Инструкция и база взаимодействий", "К": "Проверенный текст", "В": "Ответит врач",
};
const SEVERITY: Record<string, string> = {
  red: "bg-red-50 ring-red-200", yellow: "bg-amber-50 ring-amber-200", info: "bg-brand-50 ring-brand-100",
  unknown: "bg-gray-50 ring-gray-200",
};
// Кнопки-действия, которые ведут на другие экраны сайта.
const LINKS: Record<string, { href: string; label: string }> = {
  ask_doctor_form: { href: "/messages", label: "Написать врачу" },
  message_form: { href: "/messages", label: "Написать врачу" },
  open_safety_plan: { href: "/safety-plan", label: "Открыть мой план безопасности" },
  panic: { href: "/help?panic=1", label: "Открыть экран помощи" },
};

type Mode = "substance" | "new_drug" | "side_effect" | "alarming" | "attach" | null;
type Run = <T>(action: () => Promise<T>) => Promise<T | undefined>;

export default function AssistantPage() {
  const router = useRouter();
  const [tree, setTree] = useState<AssistantTree | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null);
  const [mode, setMode] = useState<Mode>(null);
  const [choices, setChoices] = useState<Record<string, string>[]>([]);
  const [alarming, setAlarming] = useState<AlarmingResult | null>(null);
  const [feedback, setFeedback] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Me>("me").then((profile) => {
      setMe(profile);
      if (!profile.has_doctor) return;
      api<AssistantTree>("me/assistant").then(setTree).catch((e) => setError(e.message));
      const open = new URLSearchParams(window.location.search).get("q"); // /assistant?q=alarming — сразу к вопросу
      if (open) ask(open);
    }).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function reset() {
    setAnswer(null);
    setMode(null);
    setAlarming(null);
    setFeedback(null);
    setError("");
  }

  const run: Run = async (action) => {
    setBusy(true);
    setError("");
    try {
      return await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  async function ask(buttonId: string) {
    reset();
    const r = await run(() => api<AssistantAnswer>("me/assistant/answers", { method: "POST", body: { button_id: buttonId } }));
    if (!r) return;
    setAnswer(r);
    window.scrollTo({ top: 0, behavior: "smooth" });
    const action = r.actions[0];
    if (action === "choose_substance") { setMode("substance"); setChoices(r.choices ?? []); }
    if (action === "choose_side_effect") { setMode("side_effect"); setChoices(r.choices ?? []); }
    if (action === "choose_alarming_symptom") { setMode("alarming"); setChoices(r.choices ?? []); }
    if (action === "add_other_medication") {
      setMode("new_drug");
      setChoices(await api<Substance[]>("me/assistant/substances").catch(() => []));
    }
    if (action === "attach_file" || action === "open_labs") setMode("attach");
  }

  function follow(next: AssistantAnswer | undefined) {
    if (!next) return;
    setAnswer(next);
    setMode(null);
  }

  async function sendFeedback(helped: boolean) {
    if (!answer) return;
    setFeedback(helped);
    await api(`me/assistant/interactions/${answer.interaction_id}/feedback`, { method: "POST", body: { helped } })
      .catch(() => null);
    if (!helped) router.push(`/messages?ask=${answer.interaction_id}&q=${encodeURIComponent(answer.label)}`);
  }

  if (me && !me.has_doctor) {
    return (
      <Shell title="Помощник">
        <MascotSays pose="standing">
          Помощник отвечает по вашей схеме лечения, поэтому он доступен после подключения к лечащему врачу.
          А пока можно пройти самопроверку самочувствия.
        </MascotSays>
        <Link href="/self-check" className="mt-4 block rounded-xl bg-brand-600 btn-3d py-3 text-center font-semibold text-white">
          Самопроверка
        </Link>
      </Shell>
    );
  }

  const findings = answer?.findings ?? [];
  return (
    <Shell title="Помощник">
      {!answer && (
        <MascotSays pose="one-wing">
          Выберите вопрос. Я отвечаю только по вашей схеме, инструкции и проверенным текстам — а если не знаю, передам врачу.
        </MascotSays>
      )}
      <ErrorText>{error}</ErrorText>

      {answer && (
        <Card className="ring-1 ring-brand-200">
          <p className="font-bold text-brand-900">{answer.label}</p>
          {answer.help_screen && <div className="mt-3"><HelpView screen={answer.help_screen} /></div>}
          {findings.length > 0 && (
            <ul className="mt-3 space-y-2">
              {findings.map((f, i) => (
                <li key={i} className={`rounded-lg p-3 text-sm ring-1 ${SEVERITY[f.severity]}`}>
                  <b>{f.first} + {f.second}</b>: {f.patient_text}
                </li>
              ))}
            </ul>
          )}
          {/* Находки по взаимодействиям уже показаны цветными карточками — их текстовые дубли пропускаем. */}
          {answer.parts.filter((p) => !findings.some((f) => p.text.endsWith(f.patient_text))).map((p, i) => (
            <div key={i} className="mt-3">
              <p className="whitespace-pre-line">{p.text}</p>
              <p className="mt-1 text-xs text-gray-500">{SOURCE[p.source] ?? p.source}{p.reference && ` · ${p.reference}`}</p>
            </div>
          ))}
          {answer.handed_to_doctor && (
            <p className="mt-3 rounded-lg bg-brand-50 p-3 text-sm text-brand-900">Вопрос передан вашему врачу — ответ придёт в «Врачу».</p>
          )}

          {answer.actions.filter((a) => LINKS[a]).map((a) => (
            <Link key={a} href={LINKS[a].href}
                  className="mt-3 block rounded-xl bg-brand-600 btn-3d py-3 text-center font-semibold text-white">
              {LINKS[a].label}
            </Link>
          ))}

          {mode === "substance" && (
            <SubstancePicker choices={choices as Substance[]} busy={busy} submitLabel="Проверить сочетание"
                             onPick={(body) => run(() => api<AssistantAnswer>("me/assistant/combinations",
                               { method: "POST", body })).then(follow)} />
          )}
          {mode === "new_drug" && (
            <SubstancePicker choices={choices as Substance[]} busy={busy} submitLabel="Добавить и сообщить врачу"
                             onPick={(body) => run(() => api<AssistantAnswer>("me/other-medications",
                               { method: "POST", body })).then(follow)} />
          )}
          {mode === "side_effect" && (
            <SideEffectPicker choices={choices} busy={busy}
                              onPick={(code, other_text) => run(() => api<AssistantAnswer>("me/assistant/side-effects",
                                { method: "POST", body: { code, other_text } })).then(follow)} />
          )}
          {mode === "alarming" && !alarming && (
            <div className="mt-3 space-y-2">
              <p className="text-sm text-gray-600">Что из этого происходит сейчас?</p>
              {choices.map((c) => (
                <button key={c.code} disabled={busy}
                        onClick={async () => {
                          const r = await run(() => api<AlarmingResult>("me/alarming-symptoms",
                            { method: "POST", body: { code: c.code } }));
                          if (r?.start_risk_protocol) router.push("/risk?trigger=alarming_symptom");
                          else if (r) setAlarming(r);
                        }}
                        className="block w-full rounded-xl bg-white px-3 py-3 text-left text-sm ring-1 ring-red-200">
                  {c.label}
                </button>
              ))}
            </div>
          )}
          {alarming && <AlarmingAdvice result={alarming} />}
          {mode === "attach" && <AttachForm busy={busy} run={run} />}

          {!mode && !alarming && (answer.parts.length > 0 || findings.length > 0) && feedback === null && (
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button onClick={() => sendFeedback(true)} className="rounded-xl bg-gray-100 py-2 text-sm font-semibold">
                {tree?.follow_up.helped ?? "Ответ помог"}
              </button>
              {!answer.handed_to_doctor && (
                <button onClick={() => sendFeedback(false)} className="rounded-xl bg-gray-100 py-2 text-sm font-semibold">
                  {tree?.follow_up.still_ask_doctor ?? "Всё равно хочу спросить врача"}
                </button>
              )}
            </div>
          )}
          {feedback === true && <p className="mt-3 text-sm text-brand-700">Спасибо! Рад, что помог.</p>}
          <button onClick={reset} className="mt-4 w-full py-2 text-sm text-brand-700">← Все вопросы</button>
        </Card>
      )}

      {!answer && tree?.blocks.map((block) => (
        <Card key={block.no}>
          <p className="font-bold text-brand-900">{block.title}</p>
          <div className="mt-2 flex flex-col gap-2">
            {block.buttons.map((b) => (
              <button key={b.id} onClick={() => ask(b.id)} disabled={busy}
                      className="rounded-xl bg-gray-50 px-3 py-3 text-left text-sm font-medium active:bg-brand-50">
                {b.label}
              </button>
            ))}
          </div>
        </Card>
      ))}
    </Shell>
  );
}

function SubstancePicker({ choices, busy, submitLabel, onPick }: {
  choices: Substance[]; busy: boolean; submitLabel: string;
  onPick: (body: { substance_id: string | null; free_name: string | null }) => void;
}) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<Substance | null>(null);
  const q = query.trim().toLowerCase();
  const found = q ? choices.filter((c) => c.name.toLowerCase().includes(q)).slice(0, 8) : [];

  return (
    <div className="mt-3">
      <input value={picked?.name ?? query} placeholder="Название препарата, БАД или «алкоголь»"
             onChange={(e) => { setPicked(null); setQuery(e.target.value); }} maxLength={100}
             className="w-full rounded-lg border border-gray-300 p-2" />
      {!picked && found.length > 0 && (
        <ul className="mt-1 divide-y rounded-lg border">
          {found.map((c) => (
            <li key={c.id}>
              <button onClick={() => setPicked(c)} className="w-full px-3 py-2 text-left text-sm">{c.name}</button>
            </li>
          ))}
        </ul>
      )}
      {!picked && q && found.length === 0 && (
        <p className="mt-1 text-xs text-gray-500">В базе такого нет — отправим название как есть, и вопрос уйдёт врачу.</p>
      )}
      <PrimaryButton disabled={busy || (!picked && !q)} className="mt-3"
                     onClick={() => onPick(picked ? { substance_id: picked.id, free_name: null }
                       : { substance_id: null, free_name: query.trim() })}>
        {submitLabel}
      </PrimaryButton>
    </div>
  );
}

function SideEffectPicker({ choices, busy, onPick }: {
  choices: Record<string, string>[]; busy: boolean; onPick: (code: string, other: string | null) => void;
}) {
  const [code, setCode] = useState<string | null>(null);
  const [other, setOther] = useState("");
  const free = Boolean(choices.find((c) => c.code === code)?.free_text);
  return (
    <div className="mt-3">
      <div className="grid grid-cols-2 gap-2">
        {choices.map((c) => (
          <button key={c.code} onClick={() => setCode(c.code)}
                  className={`rounded-lg px-2 py-2 text-sm ${code === c.code ? "bg-brand-600 btn-3d font-semibold text-white" : "bg-gray-100"}`}>
            {c.label}
          </button>
        ))}
      </div>
      {free && <textarea value={other} onChange={(e) => setOther(e.target.value)} maxLength={500} rows={3}
                         placeholder="Опишите, что беспокоит" className="mt-2 w-full rounded-lg border border-gray-300 p-2" />}
      <PrimaryButton disabled={busy || !code || (free && !other.trim())} className="mt-3"
                     onClick={() => onPick(code!, free ? other.trim() : null)}>
        Отметить
      </PrimaryButton>
    </div>
  );
}

function AlarmingAdvice({ result }: { result: AlarmingResult }) {
  return (
    <div className="mt-3 rounded-2xl bg-red-50 p-4 ring-1 ring-red-200">
      <p className="text-lg leading-relaxed">{result.patient_text}</p>
      {result.action.includes("112") && (
        <a href="tel:112" className="mt-3 block rounded-xl bg-red-600 btn-3d-red py-3 text-center text-lg font-semibold text-white">
          Позвонить 112
        </a>
      )}
      <Link href="/messages" className="mt-3 block text-center text-brand-700 underline">Написать врачу</Link>
    </div>
  );
}

/** Блок 9: заключение или фото назначений от другого врача — текст и до 5 файлов (JPEG, PNG, PDF до 10 МБ). */
function AttachForm({ busy, run }: { busy: boolean; run: Run }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sent, setSent] = useState(false);

  async function send() {
    const ok = await run(async () => {
      const r = await api<{ message: { id: string } }>("me/messages", {
        method: "POST",
        body: { client_id: newId(), origin: "block9_other_doctor", body: text.trim() || "Заключение другого врача" },
      });
      for (const file of files) await upload(`me/messages/${r.message.id}/attachments`, file);
      return true;
    });
    if (ok) setSent(true);
  }

  if (sent) return <p className="mt-3 rounded-lg bg-brand-50 p-3 text-sm text-brand-900">Отправлено врачу ✓</p>;
  return (
    <div className="mt-3">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000}
                placeholder="Что назначил другой врач (необязательно)" className="w-full rounded-lg border border-gray-300 p-2" />
      <input type="file" multiple accept="image/jpeg,image/png,application/pdf"
             onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 5))} className="mt-2 block w-full text-sm" />
      <p className="mt-1 text-xs text-gray-500">Фото (JPEG, PNG) или PDF, до 10 МБ, не больше 5 файлов.</p>
      <PrimaryButton disabled={busy || (files.length === 0 && !text.trim())} onClick={send} className="mt-3">
        Отправить врачу
      </PrimaryButton>
    </div>
  );
}
