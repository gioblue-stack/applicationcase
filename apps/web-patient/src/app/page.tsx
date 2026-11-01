// «Сегодня»: одно главное дело крупно, остальные — списком со статусами; приёмы лекарств на сегодня.
// Первый вход: выбор пингвина → «Что сейчас происходит в жизни» → этот экран.
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Shell, { Card, ErrorText, StatusChip } from "@/components/Shell";
import DoseRow from "@/components/DoseRow";
import { MascotSays } from "@/components/Mascot";
import { api } from "@/lib/client";
import { readLocal, saveHelpProfile, writeLocal } from "@/lib/local";
import { dayLabel } from "@/lib/dates";
import { themeChosen } from "@/lib/theme";
import type { Dose, Me, NextDose, SafetyPlan, Today } from "@/lib/types";

const TITLES = { PHQ9: "PHQ-9", GAD7: "GAD-7" } as const;
const STRESS_OFFERED = "mc_stress_offered"; // опросник о жизненной ситуации открывается сам только при первом заходе

type Task = { key: string; title: string; hint: string; href: string; action: string; urgent?: boolean };

/** Дела на сегодня в порядке важности: первое показывается крупно, остальные — списком. */
function tasksFor(today: Today, me: Me): Task[] {
  const tasks: Task[] = [];
  if (today.risk_block_trigger) {
    tasks.push({ key: "risk", title: "Несколько вопросов о самочувствии", urgent: true,
      hint: "После начала или смены лечения врач просит отвечать на них чаще.",
      href: `/risk?trigger=${today.risk_block_trigger}`, action: "Ответить" });
  }
  for (const code of today.weekly?.pending ?? []) {
    tasks.push({ key: code, title: `Опросник недели ${TITLES[code]}`, hint: "Около 3 минут. Врач увидит, как меняется самочувствие.",
      href: `/questionnaire/${code}`, action: "Пройти" });
  }
  if (!today.diary_entry_id) {
    tasks.push({ key: "diary", title: "Отметить самочувствие", hint: "Дневник — около минуты.", href: "/diary",
      action: "Заполнить дневник" });
  }
  if (today.stress_check_due) {
    tasks.push({ key: "stress", title: "Что сейчас происходит в жизни", hint: "2–3 минуты. Врач поймёт, что может влиять на самочувствие.",
      href: "/stress", action: "Ответить" });
  }
  if (!me.has_doctor) {
    tasks.push({ key: "self", title: "Самопроверка самочувствия", hint: "PHQ-9 и GAD-7 — около 5 минут. Это скрининг, а не диагноз.",
      href: "/self-check", action: "Пройти" });
  }
  return tasks;
}

function left(n: number) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `Осталось ${n} дело на сегодня`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `Осталось ${n} дела на сегодня`;
  return `Осталось ${n} дел на сегодня`;
}

export default function TodayPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [today, setToday] = useState<Today | null>(null);
  const [doses, setDoses] = useState<Dose[]>([]);
  const [next, setNext] = useState<NextDose[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!themeChosen()) {
      router.replace("/theme?next=/"); // первый вход на этом устройстве — сначала пингвин
      return;
    }
    try {
      const [profile, day] = await Promise.all([api<Me>("me"), api<Today>("me/today")]);
      setMe(profile);
      setToday(day);
      if (day.stress_check_due && !readLocal<boolean>(STRESS_OFFERED)) {
        writeLocal(STRESS_OFFERED, true); // «Заполню позже» не возвращает сюда снова — дальше только карточка
        router.push("/stress");
        return;
      }
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
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  const firstName = me?.full_name.split(" ")[0];
  const tasks = today && me ? tasksFor(today, me) : [];
  const [main, ...rest] = tasks;

  return (
    <Shell title={firstName ? `Здравствуйте, ${firstName}` : "Сегодня"}>
      <ErrorText>{error}</ErrorText>
      {today && me && (
        tasks.length > 0
          ? <MascotSays pose="one-wing">{left(tasks.length)}. Начнём с первого?</MascotSays>
          : <MascotSays pose="both-wings">На сегодня всё сделано. Спасибо, что отмечаете!</MascotSays>
      )}

      {main && (
        <section className={`mt-2 rounded-3xl p-6 shadow-soft ${main.urgent ? "bg-amber-50" : "bg-brand-100"}`}>
          <p className={`text-sm font-bold ${main.urgent ? "text-amber-900" : "text-brand-700"}`}>Следующий шаг</p>
          <h2 className="mt-1 text-2xl leading-tight font-extrabold text-brand-900">{main.title}</h2>
          <p className="mt-2 text-muted">{main.hint}</p>
          <Link href={main.href}
                className="btn-solid mt-5 flex items-center justify-center rounded-2xl bg-brand-600 px-5 text-lg font-bold text-white">
            {main.action}
          </Link>
        </section>
      )}

      {today && (rest.length > 0 || today.diary_entry_id) && (
        <Card className="p-2">
          <h2 className="px-3 pt-2 pb-1 text-lg font-extrabold text-brand-900">Ещё на сегодня</h2>
          <ul className="divide-y divide-line">
            {rest.map((task) => (
              <li key={task.key}>
                <Link href={task.href} className="flex min-h-14 items-center gap-3 rounded-2xl px-3 py-3 hover:bg-subtle">
                  <span className="flex-1 font-semibold">{task.title}</span>
                  <StatusChip status="waiting">Ждёт</StatusChip>
                </Link>
              </li>
            ))}
            {today.diary_entry_id && (
              <li>
                <Link href="/diary" className="flex min-h-14 items-center gap-3 rounded-2xl px-3 py-3 hover:bg-subtle">
                  <span className="flex-1 font-semibold">Дневник <span className="font-normal text-muted">· изменить ответы</span></span>
                  <StatusChip status="done">Готово</StatusChip>
                </Link>
              </li>
            )}
          </ul>
        </Card>
      )}

      {me?.takes_medication && (
        <Card>
          <h2 className="text-lg font-extrabold text-brand-900">Лекарства сегодня</h2>
          {doses.length === 0 && next.length === 0 && (
            <p className="mt-2 text-muted">На сегодня приёмов нет.</p>
          )}
          <ul className="mt-1 divide-y divide-line">
            {doses.map((dose) => (
              <DoseRow key={dose.id} dose={dose} onChange={load} />
            ))}
          </ul>
          {/* Назначение, у которого сегодня приёмов нет, — чтобы пациент видел, что оно не потерялось. */}
          {next.map((n) => (
            <p key={n.prescription_id} className="mt-2 rounded-2xl bg-brand-50 px-4 py-3 text-sm text-brand-900">
              <span className="font-bold">{n.inn}{n.trade_name && ` (${n.trade_name})`} {n.dose} {n.unit}</span>
              {" — ближайший приём "}{dayLabel(n.local_date, today!.day)} в {n.local_time}
            </p>
          ))}
        </Card>
      )}
    </Shell>
  );
}
