// Экран помощи: открывается без входа и без сети (§5.5). С ?panic=1 — ещё и сигнал врачу.
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import HelpView from "@/components/HelpView";
import { newId, nowIso } from "@/lib/client";
import { useContent } from "@/lib/content";
import { localScreen } from "@/lib/help";
import { flushPanic, helpProfile, queuePanic, type HelpProfile } from "@/lib/local";

// Если контент ещё ни разу не загрузился (первый запуск без сети) — номера всё равно на экране.
const FALLBACK = [
  { tel: "112", display: "112", service: "Единый номер экстренных служб" },
  { tel: "88001004994", display: "8-800-100-49-94", service: "Единый телефон доверия психологической помощи" },
];

export default function HelpPage() {
  const content = useContent();
  const [profile, setProfile] = useState<HelpProfile | null>(null);

  useEffect(() => {
    setProfile(helpProfile());
    if (new URLSearchParams(window.location.search).get("panic") === "1") {
      queuePanic({ client_id: newId(), pressed_at: nowIso() });
      flushPanic();
      window.history.replaceState(null, "", "/help"); // обновление страницы не должно повторять сигнал
    }
  }, []);

  const screen = content && profile
    ? localScreen(content, profile.hasDoctor ? "help" : "self_user_help", profile.region)
    : null;

  return (
    <div className="safe-top mx-auto min-h-dvh max-w-lg px-4 pb-10">
      <div className="flex items-center justify-between py-3">
        <h1 className="text-xl font-semibold">Помощь</h1>
        <Link href="/" className="text-brand-700">Закрыть</Link>
      </div>
      {screen ? (
        <HelpView screen={{ ...screen, fullscreen: true }} contacts={profile?.contacts} />
      ) : (
        <div className="rounded-2xl bg-red-50 p-5 ring-1 ring-red-200">
          <p className="text-lg">Если вам нужна помощь сейчас — позвоните:</p>
          {FALLBACK.map((p) => (
            <a key={p.tel} href={`tel:${p.tel}`}
               className="mt-3 block rounded-xl bg-red-600 btn-3d-red px-4 py-4 text-center text-lg font-semibold text-white">
              {p.display} — {p.service}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
