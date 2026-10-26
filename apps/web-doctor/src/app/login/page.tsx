"use client";
// Вход врача: пароль → код из приложения-аутентификатора (обязательно, §5.2). При первом входе — настройка TOTP.
import { useState } from "react";

type Step = "password" | "setup" | "code";

async function post(url: string, body?: unknown) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? "Ошибка входа");
  return data;
}

export default function LoginPage() {
  const [step, setStep] = useState<Step>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<{ secret: string; qr: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const submitPassword = () => run(async () => {
    const { totp_enrolled } = await post("/api/auth/login", { email, password });
    setPassword("");
    if (totp_enrolled) {
      setStep("code");
    } else {
      setSetup(await post("/api/auth/totp-setup"));
      setStep("setup");
    }
  });

  const submitCode = () => run(async () => {
    await post("/api/auth/mfa", { code });
    window.location.href = "/";
  });

  return (
    <main className="mx-auto mt-16 max-w-sm rounded-lg bg-white p-6 shadow">
      <h1 className="mb-4 text-xl font-semibold">Вход врача</h1>
      {step === "password" && (
        <form onSubmit={(e) => { e.preventDefault(); submitPassword(); }} className="space-y-3">
          <input className="w-full rounded border px-3 py-2" type="email" placeholder="E-mail" autoComplete="username"
                 aria-label="E-mail" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input className="w-full rounded border px-3 py-2" type="password" placeholder="Пароль" aria-label="Пароль"
                 autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <button className="w-full rounded bg-slate-800 py-2 text-white disabled:opacity-50" disabled={busy}>Далее</button>
        </form>
      )}
      {(step === "setup" || step === "code") && (
        <form onSubmit={(e) => { e.preventDefault(); submitCode(); }} className="space-y-3">
          {step === "setup" && setup && (
            <div className="space-y-2 text-sm">
              <p>Двухфакторный вход обязателен. Отсканируйте QR-код в приложении-аутентификаторе
                или введите ключ вручную.</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={setup.qr} alt="QR-код для приложения-аутентификатора" className="mx-auto" />
              <code className="block break-all rounded bg-slate-100 p-2 text-xs">{setup.secret}</code>
            </div>
          )}
          <input className="w-full rounded border px-3 py-2 tracking-widest" inputMode="numeric" maxLength={6}
                 autoComplete="one-time-code" placeholder="Код из приложения" aria-label="Код из приложения"
                 value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} required />
          <button className="w-full rounded bg-slate-800 py-2 text-white disabled:opacity-50"
                  disabled={busy || code.length !== 6}>Войти</button>
        </form>
      )}
      {error && <p className="mt-3 text-sm text-red-700" role="alert">{error}</p>}
    </main>
  );
}
