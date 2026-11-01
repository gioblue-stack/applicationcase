// Профиль: тема (пингвин и тёмный режим), напоминания, ответы о жизненной ситуации, установка на телефон, выход.
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Mascot from "@/components/Mascot";
import PushSettings from "@/components/PushSettings";
import Shell, { Card } from "@/components/Shell";
import { api } from "@/lib/client";
import { HELP_PROFILE, writeLocal } from "@/lib/local";
import { MODES, type Mode, THEMES, type ThemeId, applyTheme, currentMode, currentTheme } from "@/lib/theme";
import type { Me } from "@/lib/types";

export default function ProfilePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [standalone, setStandalone] = useState(false);
  const [theme, setTheme] = useState<ThemeId>("blue");
  const [mode, setMode] = useState<Mode>("system");

  useEffect(() => {
    setTheme(currentTheme());
    setMode(currentMode());
    api<Me>("me").then(setMe).catch(() => null);
    setStandalone(window.matchMedia("(display-mode: standalone)").matches);
  }, []);

  function changeMode(next: Mode) {
    setMode(next);
    applyTheme(theme, next);
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    writeLocal(HELP_PROFILE, null); // близкие из плана безопасности не остаются на телефоне после выхода
    window.location.href = "/login";
  }

  return (
    <Shell title="Профиль">
      {me && (
        <Card>
          <p className="text-xl font-extrabold text-brand-900">{me.full_name}</p>
          <p className="text-sm text-muted">{me.has_doctor ? "Подключены к лечащему врачу" : "Без лечащего врача"}</p>
        </Card>
      )}
      <Card>
        <h2 className="text-lg font-extrabold text-brand-900">Оформление</h2>
        <Link href="/theme?next=/profile" className="mt-3 flex items-center gap-4 rounded-2xl bg-brand-100 p-3 hover:bg-brand-200">
          <Mascot pose="standing" size={56} />
          <span className="flex-1">
            <span className="block font-extrabold text-brand-900">Тема «{THEMES.find((t) => t.id === theme)?.name}»</span>
            <span className="text-sm text-brand-700">Сменить пингвина</span>
          </span>
        </Link>
        <p className="mt-4 text-sm font-bold text-muted" id="mode-label">Светлое или тёмное</p>
        <div role="radiogroup" aria-labelledby="mode-label" className="mt-2 grid grid-cols-3 gap-1 rounded-2xl bg-subtle p-1">
          {MODES.map((m) => (
            <button key={m.id} type="button" role="radio" aria-checked={mode === m.id} onClick={() => changeMode(m.id)}
                    className={`min-h-11 rounded-2xl px-2 text-sm font-bold ${
                      mode === m.id ? "bg-surface text-brand-800 shadow-soft" : "text-muted"}`}>
              {m.name}
            </button>
          ))}
        </div>
      </Card>
      {me?.has_doctor && (
        <Link href="/stress" className="mt-4 block rounded-3xl border border-line/70 bg-surface p-5 font-bold text-brand-800 shadow-soft hover:bg-brand-50">
          Что сейчас происходит в жизни
          <span className="block text-sm font-normal text-muted">Обновить ответы для врача</span>
        </Link>
      )}
      <PushSettings />
      {!standalone && (
        <Card>
          <p className="font-semibold">Добавьте на экран телефона</p>
          <p className="mt-2 text-sm"><b>iPhone (Safari):</b> кнопка «Поделиться» → «На экран „Домой“» → «Добавить».</p>
          <p className="mt-2 text-sm"><b>Android (Chrome):</b> меню ⋮ → «Добавить на главный экран» или «Установить приложение».</p>
          <p className="mt-2 text-sm text-muted">Сайт будет открываться как приложение — без адресной строки.</p>
        </Card>
      )}
      <button onClick={logout}
              className="mt-6 min-h-13 w-full rounded-2xl border border-line bg-surface py-3 font-bold text-red-700 hover:bg-red-50">
        Выйти
      </button>
    </Shell>
  );
}
