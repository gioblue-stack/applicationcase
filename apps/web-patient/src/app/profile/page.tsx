// Профиль: как добавить сайт на рабочий стол телефона и выход.
"use client";

import { useEffect, useState } from "react";
import Shell, { Card } from "@/components/Shell";
import { api } from "@/lib/client";
import { HELP_PROFILE, writeLocal } from "@/lib/local";
import type { Me } from "@/lib/types";

export default function ProfilePage() {
  const [me, setMe] = useState<Me | null>(null);
  const [standalone, setStandalone] = useState(false);

  useEffect(() => {
    api<Me>("me").then(setMe).catch(() => null);
    setStandalone(window.matchMedia("(display-mode: standalone)").matches);
  }, []);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    writeLocal(HELP_PROFILE, null); // близкие из плана безопасности не остаются на телефоне после выхода
    window.location.href = "/login";
  }

  return (
    <Shell title="Профиль">
      {me && (
        <Card>
          <p className="text-lg font-semibold">{me.full_name}</p>
          <p className="text-sm text-gray-600">{me.has_doctor ? "Подключены к лечащему врачу" : "Без лечащего врача"}</p>
        </Card>
      )}
      {!standalone && (
        <Card>
          <p className="font-semibold">Добавьте на экран телефона</p>
          <p className="mt-2 text-sm"><b>iPhone (Safari):</b> кнопка «Поделиться» → «На экран „Домой“» → «Добавить».</p>
          <p className="mt-2 text-sm"><b>Android (Chrome):</b> меню ⋮ → «Добавить на главный экран» или «Установить приложение».</p>
          <p className="mt-2 text-sm text-gray-600">Сайт будет открываться как приложение — без адресной строки.</p>
        </Card>
      )}
      <button onClick={logout} className="mt-6 w-full rounded-xl bg-white py-3 text-red-700 shadow-sm">Выйти</button>
    </Shell>
  );
}
