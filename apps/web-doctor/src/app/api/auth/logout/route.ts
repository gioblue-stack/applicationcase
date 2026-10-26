import { NextResponse } from "next/server";
import { backendJson, clearSession, refreshToken } from "@/lib/server/session";

export async function POST() {
  const token = await refreshToken();
  if (token) await backendJson("auth/logout", { refresh_token: token }).catch(() => undefined);
  await clearSession();
  return new NextResponse(null, { status: 204 });
}
