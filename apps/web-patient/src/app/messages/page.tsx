// Вопрос врачу (§1.4, §2.4): до отправки — срок ответа и «это не канал экстренной связи».
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import HelpView from "@/components/HelpView";
import { MascotSays } from "@/components/Mascot";
import Shell, { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { ApiError, api, newId } from "@/lib/client";
import type { HelpScreen, Message } from "@/lib/types";

type Preface = { doctor_name: string; response_time_hours: number | null; warning: string };

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
        method: "POST", body: { client_id: clientId.current, origin: "block7_question", body: text },
      });
      setText("");
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
      <Shell title="Врачу">
        <MascotSays pose="standing">Сообщения доступны, когда вы подключены к лечащему врачу по коду приглашения.</MascotSays>
      </Shell>
    );
  }

  return (
    <Shell title="Вопрос врачу">
      {preface && (
        <Card className="bg-amber-50">
          <p className="font-semibold">{preface.doctor_name}</p>
          {preface.response_time_hours && (
            <p className="text-sm">Обычно отвечает в течение {preface.response_time_hours} ч в рабочее время.</p>
          )}
          <p className="mt-2 text-sm font-medium text-amber-950">{preface.warning}</p>
        </Card>
      )}
      {help && <div className="mt-4"><HelpView screen={help} /></div>}

      <ul className="mt-4 flex flex-col gap-2">
        {thread.map((m) => {
          const mine = m.direction === "patient_to_doctor";
          return (
            <li key={m.id}
                className={`max-w-[85%] rounded-2xl px-4 py-2 ${mine ? "self-end bg-brand-600 text-white" : "self-start bg-white shadow-sm"}`}>
              <p className="whitespace-pre-line">{m.body}</p>
              <p className={`mt-1 text-xs ${mine ? "text-brand-100" : "text-gray-400"}`}>{when(m.created_at)}</p>
            </li>
          );
        })}
      </ul>

      <form onSubmit={send}>
        <Card>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={2000} required
                    placeholder="Ваш вопрос врачу" className="w-full rounded-lg border border-gray-300 p-2" />
          <ErrorText>{error}</ErrorText>
          <PrimaryButton type="submit" disabled={busy || !text.trim()} className="mt-3">Отправить</PrimaryButton>
        </Card>
      </form>
    </Shell>
  );
}
