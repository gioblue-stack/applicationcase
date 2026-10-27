// Каркас экрана: заголовок, содержимое, кнопка «Мне сейчас очень плохо» и вкладки — на каждом экране (§5.5).
"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { flushPanic } from "@/lib/local";

const TABS = [
  { href: "/", label: "Сегодня" },
  { href: "/plan", label: "Лечение" },
  { href: "/messages", label: "Врачу" },
  { href: "/profile", label: "Профиль" },
];

export default function Shell({ title, back, children }: { title: string; back?: boolean; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    flushPanic(); // нажатия кнопки, сделанные без сети
  }, []);

  return (
    <div className="mx-auto flex min-h-dvh max-w-lg flex-col">
      <header className="safe-top sticky top-0 z-10 bg-[#faf7f0]/95 backdrop-blur">
        <div className="flex items-center gap-2 px-4 py-3">
          {back && (
            <button onClick={() => router.back()} aria-label="Назад" className="-ml-2 px-2 text-2xl text-brand-700">
              ‹
            </button>
          )}
          <h1 className="text-xl font-extrabold text-brand-900">{title}</h1>
        </div>
      </header>

      <main className="flex-1 px-4 pb-40">{children}</main>

      <div className="safe-bottom fixed inset-x-0 bottom-0 z-20 mx-auto max-w-lg border-t-2 border-brand-100 bg-white">
        <div className="px-4 pt-3">
          <Link href="/help?panic=1"
                className="block rounded-xl bg-red-600 btn-3d-red py-3 text-center text-base font-semibold text-white">
            Мне сейчас очень плохо
          </Link>
        </div>
        <nav className="grid grid-cols-4">
          {TABS.map((tab) => {
            const active = tab.href === "/" ? pathname === "/" : pathname.startsWith(tab.href);
            return (
              <Link key={tab.href} href={tab.href}
                    className={`py-3 text-center text-sm font-bold ${active ? "text-brand-600" : "text-gray-400"}`}>
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`mt-4 rounded-2xl border-2 border-brand-100 bg-white p-4 ${className}`}>{children}</section>;
}

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...props}
            className={`w-full rounded-xl bg-brand-600 btn-3d px-4 py-3 text-base font-semibold text-white disabled:opacity-50 ${props.className ?? ""}`} />
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  return children ? <p role="alert" className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{children}</p> : null;
}
