// Напоминания на телефон (Web Push): почему их нельзя включить и ключ сервера в формате браузера.

export type PushEnv = {
  secureContext: boolean; // https или localhost — иначе браузер не даёт подписаться
  supported: boolean; // есть serviceWorker, PushManager и Notification
  ios: boolean;
  standalone: boolean; // открыт с экрана «Домой»
  permission: "default" | "granted" | "denied";
};

/** Причина, по которой уведомления сейчас не включить, — понятным текстом; null — можно включать. */
export function pushBlocker(env: PushEnv): string | null {
  if (!env.secureContext) {
    return "Уведомления работают только по защищённой ссылке (https). Откройте сайт по https-адресу.";
  }
  if (env.ios && !env.standalone) {
    return "На iPhone уведомления работают, когда сайт добавлен на экран «Домой»: «Поделиться» → «На экран „Домой“», затем откройте его с иконки.";
  }
  if (!env.supported) return "Этот браузер не поддерживает уведомления. Попробуйте Chrome или Safari.";
  if (env.permission === "denied") {
    return "Уведомления запрещены в настройках браузера. Разрешите их для этого сайта и обновите страницу.";
  }
  return null;
}

/** Публичный ключ VAPID (base64url) → байты для pushManager.subscribe. */
export function keyToBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}
