// Service worker: экран помощи и контент открываются без сети (§5.5). Данные пациента не кэшируются.
const CACHE = "mc-help-v2";
const OFFLINE_PAGES = ["/help"];
const PUBLIC_CONTENT = "/api/backend/content/bootstrap";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll([...OFFLINE_PAGES, PUBLIC_CONTENT])));
  self.skipWaiting();
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
