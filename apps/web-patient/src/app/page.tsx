// «Сегодня»: дневник, опросники недели, уточняющий блок и приёмы лекарств на сегодня.
"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Shell, { Card, ErrorText } from "@/components/Shell";
import DoseRow from "@/components/DoseRow";
import { MascotSays } from "@/components/Mascot";
import { api } from "@/lib/client";
import { saveHelpProfile } from "@/lib/local";
import { dayLabel } from "@/lib/dates";
import type { Dose, Me, NextDose, SafetyPlan, Today } from "@/lib/types";

const TITLES = { PHQ9: "PHQ-9", GAD7: "GAD-7" } as const;

/** Реплика пингвина по тому, что осталось на сегодня. Без оценок самочувствия — только что сделать дальше. */
function Greeting({ today }: { today: Today }) {
  if (today.risk_block_trigger || today.weekly) {
    return <MascotSays pose="standing">Сегодня есть несколько вопросов от врача. Ответим по порядку?</MascotSays>;
  }
  if (!today.diary_entry_id) {
    return <MascotSays pose="one-wing">Как вы сегодня? Отметим самочувствие — это займёт минуту.</MascotSays>;
  }
  return <MascotSays pose="both-wings">Дневник на сегодня готов. Спасибо, что отмечаете!</MascotSays>;
}

export default function TodayPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [today, setToday] = useState<Today | null>(null);
  const [doses, setDoses] = useState<Dose[]>([]);
  const [next, setNext] = useState<NextDose[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [profile, day] = await Promise.all([api<Me>("me"), api<Today>("me/today")]);
      setMe(profile);
      setToday(day);
      saveHelpProfile({ region: profile.region_code, hasDoctor: profile.has_doctor });
      if (profile.takes_medication) {
        const [list, upcoming] = await Promise.all([
          api<Dose[]>(`me/doses?day=${day.day}`),
          // Подсказка о ближайшем приёме необязательна: без неё экран «Сегодня» работает как раньше.
          api<NextDose[]>(`me/doses/next?day=${day.day}`).catch(() => [] as NextDose[]),
        ]);
        setDoses(list);
        setNext(upcoming);
      }
      const plan = await api<SafetyPlan | null>("me/safety-plan");
      saveHelpProfile({ contacts: plan?.contacts ?? [] }); // «Позвонить близкому» на экране помощи без сети
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const firstName = me?.full_name.split(" ")[0];

  return (
    <Shell title={firstName ? `Здравствуйте, ${firstName}` : "Сегодня"}>
      <ErrorText>{error}</ErrorText>
      {today && <Greeting today={today} />}

      {today?.risk_block_trigger && (
        <Card className="ring-1 ring-amber-300">
          <p className="font-semibold">Несколько вопросов о самочувствии</p>
          <p className="mt-1 text-sm text-gray-600">После начала или смены лечения врач просит отвечать на них чаще.</p>
          <Link href={`/risk?trigger=${today.risk_block_trigger}`}
                className="mt-3 block rounded-xl bg-brand-600 btn-3d py-3 text-center font-semibold text-white">
            Ответить
          </Link>
        </Card>
      )}

      {today?.weekly && (
        <Card>
          <p className="font-semibold">Опросники недели</p>
          <p className="mt-1 text-sm text-gray-600">Около 5 минут. Ваш врач увидит, как меняется самочувствие.</p>
          <div className="mt-3 flex gap-2">
            {today.weekly.pending.map((code) => (
              <Link key={code} href={`/questionnaire/${code}`}
                    className="flex-1 rounded-xl bg-brand-600 btn-3d py-3 text-center font-semibold text-white">
                {TITLES[code]}
              </Link>
            ))}
          </div>
        </Card>
      )}

      {today && (
        <Card>
          {today.diary_entry_id ? (
            <>
              <p className="font-semibold">Дневник за сегодня заполнен ✓</p>
              <Link href="/diary" className="mt-2 inline-block text-sm text-brand-700 underline">Изменить ответы</Link>
            </>
          ) : (
            <>
              <p className="font-semibold">Отметим самочувствие?</p>
              <p className="mt-1 text-sm text-gray-600">Дневник — около минуты.</p>
              <Link href="/diary" className="mt-3 block rounded-xl bg-brand-600 btn-3d py-3 text-center font-semibold text-white">
                Заполнить дневник
              </Link>
            </>
          )}
        </Card>
      )}

      {me?.takes_medication && (
        <Card>
          <p className="font-semibold">Приём лекарств сегодня</p>
          {doses.length === 0 && next.length === 0 && (
            <p className="mt-2 text-sm text-gray-600">На сегодня приёмов нет.</p>
          )}
          <ul className="mt-2 divide-y divide-gray-100">
            {doses.map((dose) => (
              <DoseRow key={dose.id} dose={dose} onChange={load} />
            ))}
          </ul>
          {/* Назначение, у которого сегодня приёмов нет, — чтобы пациент видел, что оно не потерялось. */}
          {next.map((n) => (
            <p key={n.prescription_id} className="mt-2 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-900">
              <span className="font-semibold">{n.inn}{n.trade_name && ` (${n.trade_name})`} {n.dose} {n.unit}</span>
              {" — ближайший приём "}{dayLabel(n.local_date, today!.day)} в {n.local_time}
            </p>
          ))}
        </Card>
      )}
    </Shell>
  );
}
