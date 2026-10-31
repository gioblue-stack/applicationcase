// Регистрирует service worker: экран помощи без сети и напоминания на телефон.
// Браузер разрешает его только на https и на localhost.
"use client";

import { useEffect } from "react";

export default function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
    // В разработке worker нужен для уведомлений, но без кэша — иначе виден старый код (sw.js?dev=1).
    const url = process.env.NODE_ENV === "production" ? "/sw.js" : "/sw.js?dev=1";
    navigator.serviceWorker.register(url).catch(() => null);
  }, []);
  return null;
}
