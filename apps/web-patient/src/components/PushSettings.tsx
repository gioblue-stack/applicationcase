// «Напоминания на телефон»: включить Web Push, проверить, выключить (§5.3).
"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { api } from "@/lib/client";
import { keyToBytes, pushBlocker } from "@/lib/push";

type Status = { available: boolean; public_key: string | null; devices: number };

function environment() {
  const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  return {
    secureContext: window.isSecureContext,
    supported,
    ios: /iPhone|iPad|iPod/.test(navigator.userAgent),
    standalone: window.matchMedia("(display-mode: standalone)").matches,
    permission: (supported ? Notification.permission : "default") as NotificationPermission,
  };
}

async function currentSubscription() {
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
}

export default function PushSettings() {
  const [status, setStatus] = useState<Status | null>(null);
  const [blocker, setBlocker] = useState<string | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const env = environment();
    setBlocker(pushBlocker(env));
    try {
      setStatus(await api<Status>("me/push"));
    } catch (e) {
      setError((e as Error).message);
    }
    if (env.supported && env.secureContext) {
      setSubscribed(Boolean(await currentSubscription().catch(() => null)));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const enable = () => run(async () => {
    if ((await Notification.requestPermission()) !== "granted") {
      throw new Error("Без разрешения на уведомления напоминания не придут");
    }
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: keyToBytes(status!.public_key!) });
    await api("me/push/subscribe", { method: "POST", body: subscription.toJSON() });
    setMessage("Готово: напоминания о приёме лекарств и дневнике будут приходить на этот телефон.");
  });

  const disable = () => run(async () => {
    const subscription = await currentSubscription();
    if (subscription) {
      await api("me/push/unsubscribe", { method: "POST", body: { endpoint: subscription.endpoint } });
      await subscription.unsubscribe();
    }
    setMessage("Напоминания на этот телефон выключены.");
  });

  const test = () => run(async () => {
    const { delivered } = await api<{ delivered: number }>("me/push/test", { method: "POST" });
    setMessage(delivered > 0 ? "Отправили проверочное уведомление — оно появится через несколько секунд."
      : "Не удалось доставить: включите напоминания заново.");
  });

  return (
    <Card>
      <p className="font-semibold">Напоминания на телефон</p>
      <p className="mt-1 text-sm text-gray-600">О приёме лекарств по схеме врача и о дневнике. На экране блокировки —
        только «Пора отметить приём», без названий лекарств.</p>

      {status && !status.available && (
        <p className="mt-3 text-sm text-gray-500">Уведомления пока не настроены на сервере.</p>
      )}
      {status?.available && blocker && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{blocker}</p>}
      {status?.available && !blocker && (
        subscribed ? (
          <div className="mt-3 space-y-2">
            <p className="text-sm font-semibold text-brand-700">Включены на этом телефоне ✓</p>
            <PrimaryButton onClick={test} disabled={busy}>Прислать проверочное</PrimaryButton>
            <button onClick={disable} disabled={busy} className="w-full py-2 text-sm text-gray-500">Выключить</button>
          </div>
        ) : (
          <PrimaryButton onClick={enable} disabled={busy} className="mt-3">Включить напоминания</PrimaryButton>
        )
      )}
      {message && <p className="mt-3 rounded-lg bg-brand-50 p-3 text-sm text-brand-900">{message}</p>}
      <ErrorText>{error}</ErrorText>
    </Card>
  );
}
