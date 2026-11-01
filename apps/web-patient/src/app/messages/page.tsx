// Вопрос врачу (§1.4, §2.4): до отправки — срок ответа и «это не канал экстренной связи».
"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import HelpView from "@/components/HelpView";
import { MascotSays } from "@/components/Mascot";
import Shell, { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { ApiError, api, newId } from "@/lib/client";
import type { HelpScreen, Message } from "@/lib/types";

type Preface = { doctor_name: string; response_time_hours: number | null; warning: string };

/** «Иванова Елена Сергеевна (демо)» → «ИЕ». */
function initials(name: string) {
  return name.replace(/\(.*?\)/g, "").trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
}

function when(iso: string) {
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
}

export default function MessagesPage() {
  const [preface, setPreface] = useState<Preface | null>(null);
  const [noDoctor, setNoDoctor] = useState(false);
  const [thread, setThread] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [help, setHelp] = useState<HelpScreen | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const clientId = useRef(newId());
  const [fromAssistant, setFromAssistant] = useState<{ id: string; label: string } | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const id = q.get("ask");
    if (id) setFromAssistant({ id, label: q.get("q") ?? "" });
  }, []);

  const load = useCallback(async () => {
    try {
      setPreface(await api<Preface>("me/messages/preface"));
      setThread(await api<Message[]>("me/messages"));
    } catch (e) {
      if (e instanceof ApiError && e.status < 500) setNoDoctor(true);
      else setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ help_screen: HelpScreen | null }>("me/messages", {
        method: "POST",
        body: fromAssistant
          ? { client_id: clientId.current, origin: "still_ask_doctor", body: text, assistant_interaction_id: fromAssistant.id }
          : { client_id: clientId.current, origin: "block7_question", body: text },
      });
      setText("");
      setFromAssistant(null);
      clientId.current = newId();
      setHelp(r.help_screen); // кризисные слова → экран помощи сразу, врач получает красный флаг
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (noDoctor) {
    return (
      <Shell title="Врач">
        <MascotSays pose="standing">Сообщения доступны, когда вы подключены к лечащему врачу по коду приглашения.</MascotSays>
      </Shell>
    );
  }

  return (
    <Shell title="Врач">
      {preface && (
        <Card>
          <div className="flex items-center gap-4">
            <span aria-hidden className="flex size-14 shrink-0 items-center justify-center rounded-full bg-brand-100 text-lg font-extrabold text-brand-800">
              {initials(preface.doctor_name)}
            </span>
            <div className="min-w-0">
              <p className="text-sm text-muted">Мой врач</p>
              <p className="text-lg leading-snug font-extrabold text-brand-900">{preface.doctor_name}</p>
              {preface.response_time_hours && (
                <p className="text-sm text-muted">Обычно отвечает в течение {preface.response_time_hours} ч в рабочее время</p>
              )}
            </div>
          </div>
          <Link href="/assistant"
                className="mt-4 flex min-h-13 items-center justify-center rounded-2xl bg-brand-50 px-5 font-bold text-brand-800 hover:bg-brand-100">
            Спросить Помощника о лечении
          </Link>
          <p className="mt-4 rounded-2xl bg-amber-50 p-3 text-sm text-amber-950">{preface.warning}</p>
        </Card>
      )}
      {help && <div className="mt-4"><HelpView screen={help} /></div>}

      <ul className="mt-4 flex flex-col gap-2">
        {thread.map((m) => {
          const mine = m.direction === "patient_to_doctor";
          return (
            <li key={m.id}
                className={`max-w-[85%] rounded-3xl px-4 py-3 ${mine ? "self-end bg-brand-600 text-white" : "self-start bg-surface shadow-sm"}`}>
              {!mine && <p className="mb-1 text-xs font-bold text-brand-700">{preface?.doctor_name ?? "Врач"}</p>}
              <p className="whitespace-pre-line">{m.body}</p>
              <p className={`mt-1 text-xs ${mine ? "text-brand-100" : "text-muted"}`}>{when(m.created_at)}</p>
            </li>
          );
        })}
      </ul>

      <form onSubmit={send}>
        <Card>
          {fromAssistant && (
            <p className="mb-2 rounded-2xl bg-brand-50 p-2 text-sm text-brand-900">
              Вопрос к помощнику: «{fromAssistant.label}». Врач увидит его вместе с вашим сообщением.
            </p>
          )}
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={2000} required
                    placeholder="Ваш вопрос врачу" className="w-full rounded-2xl border border-line p-2" />
          <ErrorText>{error}</ErrorText>
          <PrimaryButton type="submit" disabled={busy || !text.trim()} className="mt-3">Отправить</PrimaryButton>
        </Card>
      </form>
    </Shell>
  );
}
