// «Выбери тему»: цвета сайта подстраиваются под пингвина. При первом входе и из «Профиля».
// Выбор сразу показывается на всём экране (предпросмотр), сохраняется по «Продолжить».
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Mascot from "@/components/Mascot";
import { HelpButton, PrimaryButton } from "@/components/Shell";
import { THEMES, type ThemeId, applyTheme, currentTheme } from "@/lib/theme";

export default function ThemePage() {
  const router = useRouter();
  const [selected, setSelected] = useState<ThemeId>("blue");
  const [next, setNext] = useState("/");

  useEffect(() => {
    setSelected(currentTheme());
    const target = new URLSearchParams(window.location.search).get("next");
    if (target?.startsWith("/") && !target.startsWith("//")) setNext(target); // только свои страницы
    return () => applyTheme(currentTheme(), undefined, { save: false }); // ушли без «Продолжить» — вернуть сохранённую
  }, []);

  function choose(id: ThemeId) {
    setSelected(id);
    applyTheme(id, undefined, { save: false });
  }

  function confirm() {
    applyTheme(selected);
    router.replace(next);
  }

  return (
    <div className="safe-top mx-auto flex min-h-dvh max-w-2xl flex-col px-5 md:px-6">
      <div className="flex justify-end pt-3"><HelpButton /></div>
      <h1 className="mt-4 text-[2rem] leading-tight font-extrabold text-brand-900">Выбери тему</h1>
      <p className="mt-2 text-lg font-semibold text-muted">Цвета приложения подстроятся под пингвина</p>

      <div role="radiogroup" aria-label="Тема" className="mt-6 grid grid-cols-2 gap-3 pb-32 sm:grid-cols-3 sm:gap-4">
        {THEMES.map((theme) => {
          const active = theme.id === selected;
          return (
            // Своя тема у каждой карточки: пингвин и цвета карточки — её, а не выбранной сейчас.
            <button key={theme.id} type="button" role="radio" aria-checked={active} data-theme={theme.id}
                    onClick={() => choose(theme.id)}
                    className={`relative flex flex-col items-center rounded-[1.75rem] bg-brand-100 px-3 pt-5 pb-4 text-left transition-shadow ${
                      active ? "ring-[3px] ring-brand-700" : "ring-1 ring-transparent hover:ring-brand-300"}`}>
              <Mascot pose="one-wing" size={112} />
              <span className="mt-3 flex w-full items-center justify-between gap-2 px-1">
                <span className="min-w-0 text-lg font-extrabold break-words text-brand-800 sm:text-xl">{theme.name}</span>
                <span aria-hidden className={`flex size-8 shrink-0 items-center justify-center rounded-full ${
                  active ? "bg-brand-700 text-white" : "border-2 border-brand-700"}`}>
                  {active && (
                    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth={3}
                         strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
                  )}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="safe-bottom fixed inset-x-0 bottom-0 border-t border-line/70 bg-canvas/95 backdrop-blur">
        <div className="mx-auto max-w-2xl px-5 py-4 md:px-6">
          <PrimaryButton onClick={confirm} className="min-h-14 rounded-full text-lg">Продолжить</PrimaryButton>
        </div>
      </div>
    </div>
  );
}
