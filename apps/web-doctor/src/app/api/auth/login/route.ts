// Первый фактор: e-mail и пароль. Токен для второго фактора — в httpOnly-cookie.
import { NextResponse } from "next/server";
import { backendJson, saveMfaToken } from "@/lib/server/session";

export async function POST(request: Request) {
  const { email, password } = await request.json();
  const response = await backendJson("auth/doctor/login", { email, password });
  const data = await response.json();
  if (!response.ok) return NextResponse.json(data, { status: response.status });
  await saveMfaToken(data.mfa_token);
  return NextResponse.json({ totp_enrolled: data.totp_enrolled });
}
