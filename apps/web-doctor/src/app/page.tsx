"use client";
// Главный экран врача — очередь по срочности, а не алфавитный список (§1.1).
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { FlagPush } from "@/components/FlagPush";
import { Header } from "@/components/Header";
import { NewPatient } from "@/components/NewPatient";
import { api } from "@/lib/client";
import { COLOR_DOT, COLOR_LABEL, FLAG_REASON, formatDateTime } from "@/lib/labels";
import type { QueueItem } from "@/lib/types";

type Unread = { count: number; crisis: boolean };

function plural(n: number) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "новое сообщение";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "новых сообщения";
  return "новых сообщений";
}

export default function QueuePage() {
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [unread, setUnread] = useState<Record<string, Unread>>({});

  const loadQueue = useCallback(() => {
    api<QueueItem[]>("doctor/patients").then(setItems).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    loadQueue();
    // Непрочитанные сообщения пациентов — значок рядом с именем; ошибка здесь очередь не ломает.
    api<{ patient_id: string; crisis_match: boolean }[]>("doctor/messages?status=new")
      .then((list) => {
        const byPatient: Record<string, Unread> = {};
        for (const m of list) {
          const u = (byPatient[m.patient_id] ??= { count: 0, crisis: false });
          u.count += 1;
          u.crisis ||= m.crisis_match;
        }
        setUnread(byPatient);
      })
      .catch(() => null);
  }, [loadQueue]);

  return (
    <>
      <Header />
      <main className="mx-auto max-w-5xl p-6">
        <FlagPush />
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold">Очередь пациентов</h1>
          <NewPatient onCreated={loadQueue} />
        </div>
        {error && <p role="alert" className="text-red-700">{error}</p>}
        {!items && !error && <p className="text-slate-500">Загрузка…</p>}
        {items?.length === 0 && <p className="text-slate-500">Пациентов пока нет.</p>}
        <ul className="divide-y rounded-lg bg-white shadow">
          {items?.map((item) => (
            <li key={item.patient_id}>
              <Link href={`/patients/${item.patient_id}`} className="flex items-start gap-4 p-4 hover:bg-slate-50">
                <span className={`mt-1.5 h-3 w-3 shrink-0 rounded-full ${COLOR_DOT[item.color]}`}
                      aria-label={COLOR_LABEL[item.color]} title={COLOR_LABEL[item.color]} />
                <div className="flex-1">
                  <div className="font-medium">
                    {item.full_name}
                    {!item.connected && <span className="ml-2 text-xs text-slate-500">ещё не вошёл по приглашению</span>}
                    {unread[item.patient_id] && (
                      <span className={`ml-2 rounded px-2 py-0.5 text-xs ${
                        unread[item.patient_id].crisis ? "bg-red-100 text-red-800" : "bg-blue-100 text-blue-800"}`}>
                        ✉ {unread[item.patient_id].count} {plural(unread[item.patient_id].count)}
                      </span>
                    )}
                  </div>
                  {(item.open_flags ?? []).map((flag) => (
                    <div key={flag.flag_id} className="text-sm text-slate-700">
                      {FLAG_REASON[flag.reason] ?? flag.reason}
                      <span className="ml-2 text-xs text-slate-500">{formatDateTime(flag.created_at)}</span>
                    </div>
                  ))}
                  {(item.open_flags ?? []).length === 0 && <div className="text-sm text-slate-500">Плановое наблюдение</div>}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </>
  );
}
