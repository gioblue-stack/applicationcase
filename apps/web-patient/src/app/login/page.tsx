// Вход пациента по одноразовому коду; первый вход — с кодом приглашения от врача и согласием (§5.2).
"use client";

import Link from "next/link";
import { useState } from "react";
import { ErrorText, PrimaryButton } from "@/components/Shell";
import { useContent } from "@/lib/content";

async function post(path: string, body: unknown) {
  const response = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : "Проверьте данные и попробуйте ещё раз");
  }
  return data;
}

export default function LoginPage() {
  const content = useContent();
  const [step, setStep] = useState<"login" | "code">("login");
  const [login, setLogin] = useState("");
  const [code, setCode] = useState("");
  const [firstTime, setFirstTime] = useState(false);
  const [invite, setInvite] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function requestCode(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await post("/api/auth/code", { login: login.trim() });
      setStep("code");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await post("/api/auth/login", firstTime
        ? { login: login.trim(), code: code.trim(), invite_code: invite.trim(), consent_accepted: consent,
            consent_version: content?.consent.version }
        : { login: login.trim(), code: code.trim() });
      window.location.href = "/";
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="safe-top mx-auto flex min-h-dvh max-w-lg flex-col px-4 pb-10">
      <h1 className="mt-10 text-2xl font-semibold">Дневник самочувствия</h1>
      <p className="mt-2 text-gray-600">Дневник, опросники и приём лекарств — вместе с вашим врачом.</p>

      {step === "login" ? (
        <form onSubmit={requestCode} className="mt-8 rounded-2xl bg-white p-5 shadow-sm">
          <label className="block text-sm font-medium" htmlFor="login">Телефон или e-mail</label>
          <input id="login" value={login} onChange={(e) => setLogin(e.target.value)} required autoComplete="username"
                 inputMode="email" placeholder="+7 900 000-00-00"
                 className="mt-2 w-full rounded-xl border border-gray-300 px-3 py-3 text-lg" />
          <PrimaryButton type="submit" disabled={busy || !login.trim()} className="mt-4">Получить код</PrimaryButton>
          <ErrorText>{error}</ErrorText>
        </form>
      ) : (
        <form onSubmit={signIn} className="mt-8 rounded-2xl bg-white p-5 shadow-sm">
          <p className="text-sm text-gray-600">Код отправлен на {login}.</p>
          <label className="mt-3 block text-sm font-medium" htmlFor="code">Код из сообщения</label>
          <input id="code" value={code} onChange={(e) => setCode(e.target.value)} required inputMode="numeric"
                 autoComplete="one-time-code" maxLength={8}
                 className="mt-2 w-full rounded-xl border border-gray-300 px-3 py-3 text-center text-2xl tracking-widest" />

          <label className="mt-4 flex items-center gap-3 text-sm">
            <input type="checkbox" checked={firstTime} onChange={(e) => setFirstTime(e.target.checked)} className="size-5" />
            Вхожу впервые, у меня есть код приглашения от врача
          </label>
          {firstTime && (
            <div className="mt-3">
              <label className="block text-sm font-medium" htmlFor="invite">Код приглашения</label>
              <input id="invite" value={invite} onChange={(e) => setInvite(e.target.value)} required
                     autoCapitalize="characters" className="mt-2 w-full rounded-xl border border-gray-300 px-3 py-3 text-lg" />
              {content && (
                <div className="mt-4 rounded-xl bg-gray-50 p-3 text-sm leading-relaxed text-gray-700">
                  <p className="font-semibold">{content.consent.title}</p>
                  {content.consent.paragraphs.map((p) => <p key={p} className="mt-2">{p}</p>)}
                </div>
              )}
              <label className="mt-3 flex items-start gap-3 text-sm">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} required
                       className="mt-0.5 size-5" />
                Я прочитал(а) и даю согласие на обработку данных о здоровье
              </label>
            </div>
          )}
          <PrimaryButton type="submit" disabled={busy || !code.trim() || (firstTime && (!consent || !invite.trim()))}
                         className="mt-4">
            Войти
          </PrimaryButton>
          <button type="button" onClick={() => { setStep("login"); setCode(""); setError(""); }}
                  className="mt-3 w-full text-sm text-teal-700">Изменить телефон или e-mail</button>
          <ErrorText>{error}</ErrorText>
        </form>
      )}

      {content && <p className="mt-6 text-center text-xs text-gray-500">{content.disclaimer}</p>}
      <Link href="/help" className="mt-auto block rounded-xl bg-red-600 py-3 text-center font-semibold text-white">
        Мне сейчас очень плохо
      </Link>
    </div>
  );
}
