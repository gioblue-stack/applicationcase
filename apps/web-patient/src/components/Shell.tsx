// Каркас экрана: шапка с кнопкой «Мне сейчас очень плохо» (на каждом экране, §5.5), содержимое и навигация —
// 4 вкладки внизу на телефоне, те же разделы в верхнем меню на компьютере. Общие компоненты — ниже.
"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { flushPanic } from "@/lib/local";

const ICONS = {
  today: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  plan: "M10.5 3.5a5 5 0 0 1 7.07 7.07l-7.07 7.07a5 5 0 0 1-7.07-7.07zM7 7l7.07 7.07",
  doctor: "M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H9l-5 4z",
  profile: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
};

// «Врач» объединяет переписку и Помощника: оба — про вопросы о лечении.
const TABS = [
  { href: "/", label: "Сегодня", icon: ICONS.today, match: (p: string) => p === "/" },
  { href: "/plan", label: "Лечение", icon: ICONS.plan, match: (p: string) => p.startsWith("/plan") || p.startsWith("/safety-plan") },
  { href: "/messages", label: "Врач", icon: ICONS.doctor,
    match: (p: string) => p.startsWith("/messages") || p.startsWith("/assistant") },
  { href: "/profile", label: "Профиль", icon: ICONS.profile, match: (p: string) => p.startsWith("/profile") },
];

function Icon({ d, className = "size-6" }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="none" stroke="currentColor" strokeWidth={1.8}
         strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

export function HelpButton() {
  return (
    <Link href="/help?panic=1" aria-label="Мне сейчас очень плохо — открыть экран помощи"
          className="inline-flex min-h-11 shrink-0 items-center rounded-full bg-help px-4 text-sm font-bold text-white hover:bg-help-dark">
      <span className="sm:hidden">Мне плохо</span>
      <span className="hidden sm:inline">Мне сейчас очень плохо</span>
    </Link>
  );
}

export default function Shell({ title, back, children }: { title: string; back?: boolean; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    flushPanic(); // нажатия кнопки, сделанные без сети
  }, []);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="safe-top sticky top-0 z-20 border-b border-line/70 bg-canvas/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3 md:px-6">
          {back && (
            <button onClick={() => router.back()} aria-label="Назад"
                    className="-ml-2 inline-flex size-11 items-center justify-center rounded-full text-brand-700 hover:bg-brand-50">
              <Icon d="M15 5l-7 7 7 7" />
            </button>
          )}
          <h1 className="min-w-0 flex-1 truncate text-xl font-extrabold text-brand-900 md:flex-none md:text-2xl">{title}</h1>
          <nav aria-label="Разделы" className="ml-auto hidden items-center gap-1 md:flex">
            {TABS.map((tab) => {
              const active = tab.match(pathname);
              return (
                <Link key={tab.href} href={tab.href} aria-current={active ? "page" : undefined}
                      className={`inline-flex min-h-11 items-center gap-2 rounded-full px-4 font-bold ${
                        active ? "bg-brand-100 text-brand-800" : "text-muted hover:bg-subtle"}`}>
                  <Icon d={tab.icon} className="size-5" />
                  {tab.label}
                </Link>
              );
            })}
          </nav>
          <HelpButton />
        </div>
      </header>

      <main className="mx-auto w-full max-w-2xl flex-1 px-4 pb-32 md:px-6 md:pb-16">{children}</main>

      <nav aria-label="Разделы"
           className="safe-bottom fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface/95 backdrop-blur md:hidden">
        <div className="mx-auto grid max-w-lg grid-cols-4">
          {TABS.map((tab) => {
            const active = tab.match(pathname);
            return (
              <Link key={tab.href} href={tab.href} aria-current={active ? "page" : undefined}
                    className={`flex min-h-16 flex-col items-center justify-center gap-1 text-xs font-bold ${
                      active ? "text-brand-700" : "text-muted"}`}>
                <span className={`flex h-8 w-14 items-center justify-center rounded-full ${active ? "bg-brand-100" : ""}`}>
                  <Icon d={tab.icon} />
                </span>
                {tab.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`mt-4 rounded-3xl border border-line/70 bg-surface p-5 shadow-soft ${className}`}>{children}</section>;
}

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...props}
            className={`w-full rounded-2xl bg-brand-600 btn-solid px-5 py-3 text-base font-bold text-white disabled:opacity-50 ${props.className ?? ""}`} />
  );
}

export function SecondaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...props}
            className={`min-h-13 w-full rounded-2xl bg-brand-50 px-5 py-3 text-base font-bold text-brand-800 hover:bg-brand-100 disabled:opacity-50 ${props.className ?? ""}`} />
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  return children ? <p role="alert" className="mt-3 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">{children}</p> : null;
}

export type Status = "done" | "waiting" | "missed" | "changed" | "neutral";

const STATUS_STYLE: Record<Status, { icon: string; className: string }> = {
  done: { icon: "✓", className: "bg-emerald-50 text-emerald-800" },
  waiting: { icon: "○", className: "bg-amber-50 text-amber-900" },
  missed: { icon: "✕", className: "bg-subtle text-muted" },
  changed: { icon: "↺", className: "bg-brand-50 text-brand-800" },
  neutral: { icon: "•", className: "bg-subtle text-muted" },
};

/** Статус словом и значком, не только цветом. Цвета статусов от темы не зависят. */
export function StatusChip({ status, children }: { status: Status; children: React.ReactNode }) {
  const style = STATUS_STYLE[status];
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-bold ${style.className}`}>
      <span aria-hidden>{style.icon}</span>
      {children}
    </span>
  );
}
