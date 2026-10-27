// «Мой план лечения» простым языком (§2.2) и ссылка на план безопасности.
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MascotSays } from "@/components/Mascot";
import Shell, { Card, ErrorText } from "@/components/Shell";
import { api } from "@/lib/client";
import type { PlanItem } from "@/lib/types";

const FOOD: Record<string, string> = { before: "до еды", after: "после еды", any: "независимо от еды" };

export default function PlanPage() {
  const [items, setItems] = useState<PlanItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<PlanItem[]>("me/plan").then(setItems).catch((e) => setError((e as Error).message));
  }, []);

  return (
    <Shell title="Лечение">
      <ErrorText>{error}</ErrorText>
      {items?.length === 0 && <MascotSays pose="standing">Врач пока не назначил лекарства. Когда назначит — схема появится здесь.</MascotSays>}
      {items?.map((p) => (
        <Card key={p.prescription_id}>
          <p className="text-lg font-semibold">{p.inn}{p.trade_name && ` (${p.trade_name})`}</p>
          <p className="mt-1">{p.current_dose} {p.unit}, {p.form} — в {p.times.join(", ")}</p>
          {p.with_food && FOOD[p.with_food] && <p className="text-sm text-gray-600">{FOOD[p.with_food]}</p>}
          {p.instructions && <p className="mt-2 text-sm">{p.instructions}</p>}
          {p.upcoming.length > 0 && (
            <div className="mt-3 rounded-lg bg-brand-50 p-3 text-sm">
              <p className="font-semibold">Дальше по плану</p>
              {p.upcoming.map((u) => <p key={u}>{u}</p>)}
            </div>
          )}
          <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm">
            <p className="font-semibold">Если пропустили приём</p>
            <p>{p.missed_dose_rule_text}</p>
          </div>
        </Card>
      ))}
      <Link href="/safety-plan" className="mt-4 block rounded-2xl bg-white p-4 font-semibold text-brand-800 shadow-sm">
        Мой план безопасности →
      </Link>
    </Shell>
  );
}
