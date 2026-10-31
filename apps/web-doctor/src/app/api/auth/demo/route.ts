// ВРЕМЕННО, для презентации: вход демо-врача без пароля и TOTP. Работает, только пока на API включён MC_DEMO_LOGIN.
import { NextResponse } from "next/server";
import { API_URL, backendJson, saveTokens } from "@/lib/server/session";

export async function GET() {
  const response = await fetch(`${API_URL}/api/v1/auth/demo`, { cache: "no-store" }).catch(() => null);
  if (!response?.ok) return NextResponse.json({ enabled: false });
  const data = await response.json();
  return NextResponse.json({ enabled: Boolean(data.doctor) });
}

export async function POST() {
  const response = await backendJson("auth/demo/login", { who: "doctor" });
  const data = await response.json();
  if (!response.ok) return NextResponse.json(data, { status: response.status });
  if (data.role !== "doctor") return NextResponse.json({ detail: "Демо-вход недоступен" }, { status: 403 });
  await saveTokens(data);
  return NextResponse.json({ ok: true });
}
