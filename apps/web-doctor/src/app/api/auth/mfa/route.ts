// Второй фактор: код из приложения-аутентификатора. Токены сессии — только в httpOnly-cookie.
import { NextResponse } from "next/server";
import { backendJson, mfaToken, saveTokens } from "@/lib/server/session";

export async function POST(request: Request) {
  const token = await mfaToken();
  if (!token) return NextResponse.json({ detail: "Начните вход заново" }, { status: 401 });
  const { code } = await request.json();
  const response = await backendJson("auth/doctor/mfa", { mfa_token: token, code });
  const data = await response.json();
  if (!response.ok) return NextResponse.json(data, { status: response.status });
  await saveTokens(data);
  return NextResponse.json({ ok: true });
}
