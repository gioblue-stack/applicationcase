// Цвет панели браузера под выбранного пингвина и тёмный режим; следит за сменой темы телефона.
"use client";

import { useEffect } from "react";
import { applyTheme, currentMode, currentTheme } from "@/lib/theme";

export default function ThemeSync() {
  useEffect(() => {
    const sync = () => applyTheme(currentTheme(), currentMode(), { save: false });
    sync();
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  return null;
}
