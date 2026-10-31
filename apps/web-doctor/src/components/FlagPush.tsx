"use client";
// Уведомления врачу о красных и жёлтых флагах в браузере (Web Push). Текст — без имени пациента (§2.2).
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/client";

type Status = { available: boolean; public_key: string | null; devices: number };

/** Публичный ключ VAPID (base64url) → байты для pushManager.subscribe. */
function keyToBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

function blocker(): string | null {
  if (!window.isSecureContext) return "Уведомления работают только по https или на localhost.";
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return "Этот браузер не поддерживает уведомления.";
  if (Notification.permission === "denied") return "Уведомления запрещены в настройках браузера для этого сайта.";
  return null;
}

async function registration() {
  await navigator.serviceWorker.register("/sw.js");
  return navigator.serviceWorker.ready;
}

export function FlagPush() {
  const [status, setStatus] = useState<Status | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const why = blocker();
    setReason(why);
    setStatus(await api<Status>("doctor/push").catch(() => null));
    if (!why) {
      const existing = await navigator.serviceWorker.getRegistration("/sw.js");
      setSubscribed(Boolean(await existing?.pushManager.getSubscription()));
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function run(action: () => Promise<string>) {
    setBusy(true);
    try {
      setMessage(await action());
      await refresh();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const enable = () => run(async () => {
    if ((await Notification.requestPermission()) !== "granted") throw new Error("Без разрешения уведомления не придут");
    const sub = await (await registration()).pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: keyToBytes(status!.public_key!) });
    await api("doctor/push/subscribe", { method: "POST", body: sub.toJSON() });
    return "Готово: о новых красных и жёлтых флагах придёт уведомление.";
  });

  const disable = () => run(async () => {
    const sub = await (await registration()).pushManager.getSubscription();
    if (sub) {
      await api("doctor/push/unsubscribe", { method: "POST", body: { endpoint: sub.endpoint } });
      await sub.unsubscribe();
    }
    return "Уведомления в этом браузере выключены.";
  });

  const test = () => run(async () => {
    const { delivered } = await api<{ delivered: number }>("doctor/push/test", { method: "POST" });
    return delivered > 0 ? "Проверочное уведомление отправлено." : "Не удалось доставить — включите заново.";
  });

  if (!status?.available) return null; // на сервере нет ключей VAPID — блок не показываем
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg bg-white p-3 text-sm shadow">
      <span className="font-medium">Уведомления о флагах</span>
      {reason ? <span className="text-amber-800">{reason}</span> : subscribed ? (
        <>
          <span className="text-emerald-700">включены в этом браузере ✓</span>
          <button onClick={test} disabled={busy} className="rounded border px-2 py-1">Проверить</button>
          <button onClick={disable} disabled={busy} className="text-slate-500">Выключить</button>
        </>
      ) : (
        <button onClick={enable} disabled={busy} className="rounded bg-slate-800 px-3 py-1 text-white">Включить</button>
      )}
      {message && <span className="text-slate-600">{message}</span>}
    </div>
  );
}
