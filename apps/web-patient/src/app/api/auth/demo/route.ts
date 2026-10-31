// ВРЕМЕННО, для презентации: вход за демо-пациента без кода. Работает, только пока на API включён MC_DEMO_LOGIN.
import { NextResponse } from "next/server";
import { API_URL, PATIENT_ROLES, backendJson, saveTokens, type TokenPair } from "@/lib/server/session";

export async function GET() {
  const response = await fetch(`${API_URL}/api/v1/auth/demo`, { cache: "no-store" }).catch(() => null);
  if (!response?.ok) return NextResponse.json({ enabled: false, patients: [] });
  const data = await response.json();
  return NextResponse.json({ enabled: data.patients.length > 0, patients: data.patients });
}

export async function POST(request: Request) {
  const { who } = await request.json();
  if (who === "doctor") return NextResponse.json({ detail: "Этот вход — для пациентов" }, { status: 403 });
  const response = await backendJson("auth/demo/login", { who });
  const data = await response.json();
  if (!response.ok) return NextResponse.json(data, { status: response.status });
  if (!PATIENT_ROLES.has((data as TokenPair).role)) {
    return NextResponse.json({ detail: "Этот вход — для пациентов" }, { status: 403 });
  }
  await saveTokens(data as TokenPair);
  return NextResponse.json({ ok: true });
}
