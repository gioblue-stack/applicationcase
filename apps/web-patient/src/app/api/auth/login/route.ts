// Вход по коду (есть аккаунт) или регистрация по коду приглашения врача с согласием.
import { NextResponse } from "next/server";
import { PATIENT_ROLES, backendJson, saveTokens, type TokenPair } from "@/lib/server/session";

export async function POST(request: Request) {
  const { login, code, invite_code, consent_accepted, consent_version } = await request.json();
  const response = invite_code
    ? await backendJson("auth/register/patient", { login, code, invite_code, consent_accepted, consent_version })
    : await backendJson("auth/login", { login, code });
  const data = await response.json();
  if (!response.ok) return NextResponse.json(data, { status: response.status });
  if (!PATIENT_ROLES.has((data as TokenPair).role)) {
    // Врач входит в свой кабинет по паролю и TOTP, а не здесь.
    return NextResponse.json({ detail: "Этот вход — для пациентов" }, { status: 403 });
  }
  await saveTokens(data as TokenPair);
  return NextResponse.json({ ok: true });
}
