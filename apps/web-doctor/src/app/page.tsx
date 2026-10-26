"use client";
// Главный экран врача — очередь по срочности, а не алфавитный список (§1.1).
import Link from "next/link";
import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { api } from "@/lib/client";
import { COLOR_DOT, COLOR_LABEL, FLAG_REASON, formatDateTime } from "@/lib/labels";
import type { QueueItem } from "@/lib/types";

export default function QueuePage() {
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<QueueItem[]>("doctor/patients").then(setItems).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <Header />
      <main className="mx-auto max-w-5xl p-6">
        <h1 className="mb-4 text-2xl font-semibold">Очередь пациентов</h1>
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
