"use client";
// Переписка с пациентом (§1.4): врач видит вопросы пациента и отвечает своими словами.
// Открытие переписки отмечает сообщения пациента прочитанными; ответ — отвеченными, пациенту уходит нейтральный push.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/client";
import { formatDateTime } from "@/lib/labels";

type ChatMessage = {
  id: string;
  direction: "patient_to_doctor" | "doctor_to_patient";
  origin: string;
  body: string;
  status: string;
  crisis_match: boolean;
  created_at: string;
  attachments: { id: string; mime: string; size_bytes: number }[];
};

const ORIGIN: Record<string, string> = {
  block7_question: "Вопрос врачу",
  block9_other_doctor: "Назначение другого врача",
  still_ask_doctor: "Вопрос после ответа ассистента",
  assistant_handoff: "Передано ассистентом",
};

const MAX = 5000;

export function DoctorChat({ patientId }: { patientId: string }) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      setMessages(await api<ChatMessage[]>(`doctor/patients/${patientId}/messages`));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [patientId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "nearest" }); }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`doctor/patients/${patientId}/messages`, { method: "POST", body: { body: text } });
      setText("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded border bg-white">
      <div className="max-h-96 space-y-2 overflow-y-auto p-3">
        {messages?.length === 0 && <p className="text-sm text-slate-500">Сообщений пока нет. Можно написать первым.</p>}
        {messages?.map((m) => {
          const mine = m.direction === "doctor_to_patient";
          return (
            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${
                mine ? "bg-slate-800 text-white" : m.crisis_match ? "bg-red-50 ring-1 ring-red-300" : "bg-slate-100"}`}>
                {!mine && (
                  <p className="mb-1 text-xs text-slate-500">
                    {ORIGIN[m.origin] ?? "Сообщение пациента"}
                    {m.crisis_match && <span className="ml-2 font-semibold text-red-700">кризисные слова</span>}
                  </p>
                )}
                <p className="whitespace-pre-line">{m.body}</p>
                {m.attachments.map((a) => (
                  <a key={a.id} href={`/api/backend/doctor/attachments/${a.id}`}
                     className={`mt-1 block text-xs underline ${mine ? "text-slate-200" : "text-slate-700"}`}>
                    Вложение ({a.mime}, {Math.ceil(a.size_bytes / 1024)} КБ)
                  </a>
                ))}
                <p className={`mt-1 text-xs ${mine ? "text-slate-300" : "text-slate-400"}`}>{formatDateTime(m.created_at)}</p>
              </div>
            </div>
          );
        })}
        <div ref={bottom} />
      </div>
      <form onSubmit={send} className="flex items-end gap-2 border-t p-3">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={MAX} required
                  placeholder="Сообщение пациенту" className="flex-1 rounded border px-2 py-1 text-sm" />
        <button disabled={busy || !text.trim()}
                className="rounded bg-slate-800 px-4 py-2 text-sm text-white disabled:opacity-50">
          Отправить
        </button>
      </form>
      {error && <p role="alert" className="px-3 pb-3 text-sm text-red-700">{error}</p>}
    </div>
  );
}
