// Выход: отзываем refresh-токен на сервере и удаляем cookie.
import { NextResponse } from "next/server";
import { backendJson, clearSession, refreshToken } from "@/lib/server/session";

export async function POST() {
  const token = await refreshToken();
  if (token) await backendJson("auth/logout", { refresh_token: token }).catch(() => null);
  await clearSession();
  return NextResponse.json({ ok: true });
}
