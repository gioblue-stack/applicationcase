"use client";
// Шапка кабинета и автоматический выход при бездействии (§5.6).
import Link from "next/link";
import { useEffect } from "react";

export const IDLE_LOGOUT_MS = 30 * 60_000;

async function logout() {
  await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
  window.location.href = "/login";
}

export function Header() {
  useEffect(() => {
    let timer = window.setTimeout(logout, IDLE_LOGOUT_MS);
    const reset = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(logout, IDLE_LOGOUT_MS);
    };
    const events = ["mousemove", "keydown", "click", "scroll", "touchstart"] as const;
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    return () => {
      window.clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, []);

  return (
    <header className="flex items-center justify-between border-b bg-white px-6 py-3">
      <Link href="/" className="font-semibold">Пациенты</Link>
      <button onClick={logout} className="text-sm text-slate-600 hover:text-slate-900">Выйти</button>
    </header>
  );
}
