// Service worker: экран помощи и контент открываются без сети (§5.5). Данные пациента не кэшируются.
const CACHE = "mc-help-v2";
const OFFLINE_PAGES = ["/help"];
const PUBLIC_CONTENT = "/api/backend/content/bootstrap";
// В разработке (sw.js?dev=1) — только уведомления, без кэша: иначе виден старый код.
const DEV = new URL(self.location.href).searchParams.has("dev");

self.addEventListener("install", (event) => {
  if (!DEV) event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll([...OFFLINE_PAGES, PUBLIC_CONTENT])));
  self.skipWaiting();
});

// Напоминание с сервера (Web Push). Текст уже нейтральный — без препаратов и диагноза (§2.2).
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Напоминание", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: data.tag || "reminder", // новое напоминание того же вида заменяет старое, а не копится
      data: { url: data.url || "/" },
    }),
  );
});

// Нажатие на уведомление: открыть нужный экран в уже открытом окне сайта или в новом.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => w.url.startsWith(self.location.origin));
      if (open) return open.navigate(url).then((w) => (w || open).focus());
      return self.clients.openWindow(url);
    }),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

function networkFirst(request, cacheKey) {
  return fetch(request)
    .then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(cacheKey ?? request, copy));
      }
      return response;
    })
    .catch(() => caches.match(cacheKey ?? request));
}

self.addEventListener("fetch", (event) => {
  if (DEV) return;
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname === PUBLIC_CONTENT) {
    event.respondWith(networkFirst(request));
  } else if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    // Скрипты и стили нужны, чтобы /help отрисовался без сети. Из кэша — только когда сети нет:
    // иначе после обновления сайта телефон показывал бы старую версию.
    event.respondWith(networkFirst(request));
  } else if (request.mode === "navigate") {
    // Любая страница без сети → экран помощи; ответы /api/backend/me… не кэшируются.
    const key = url.pathname === "/help" ? "/help" : undefined;
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (key && response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(key, copy));
          }
          return response;
        })
        .catch(() => caches.match("/help")),
    );
  }
});
