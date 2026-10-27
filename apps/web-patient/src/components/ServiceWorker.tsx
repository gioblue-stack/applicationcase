// Регистрирует service worker (экран помощи без сети). Браузер разрешает его на https и на localhost.
"use client";

import { useEffect } from "react";

export default function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
    if (process.env.NODE_ENV !== "production") {
      // В разработке кэш мешает видеть свежий код — снимаем ранее установленный worker.
      navigator.serviceWorker.getRegistrations().then((list) => list.forEach((r) => r.unregister()));
      return;
    }
    navigator.serviceWorker.register("/sw.js").catch(() => null);
  }, []);
  return null;
}
