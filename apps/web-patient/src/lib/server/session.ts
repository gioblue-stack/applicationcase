// Только сервер: токены пациента живут в httpOnly-cookie и в браузерный JavaScript не попадают.
import "server-only";
import { cookies } from "next/headers";

export const API_URL = process.env.MC_API_URL ?? "http://127.0.0.1:8000";

// Cookie привязаны к хосту, а не к порту: имена отличаются от кабинета врача (localhost:3000).
const ACCESS = "mcp_access";
const REFRESH = "mcp_refresh";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  access_expires_at: string;
  refresh_expires_at: string;
  role: string;
};

export const PATIENT_ROLES = new Set(["patient", "self_user"]);

function cookieOptions(expires: Date) {
  return {
    httpOnly: true,
    sameSite: "lax" as const, // ярлык на рабочем столе открывает сайт «извне» — strict потерял бы сессию
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires,
  };
}

export async function saveTokens(tokens: TokenPair) {
  const jar = await cookies();
  jar.set(ACCESS, tokens.access_token, cookieOptions(new Date(tokens.access_expires_at)));
  jar.set(REFRESH, tokens.refresh_token, cookieOptions(new Date(tokens.refresh_expires_at)));
}

export async function clearSession() {
  const jar = await cookies();
  for (const name of [ACCESS, REFRESH]) jar.delete(name);
}

export async function accessToken(): Promise<string | undefined> {
  return (await cookies()).get(ACCESS)?.value;
}

export async function refreshToken(): Promise<string | undefined> {
  return (await cookies()).get(REFRESH)?.value;
}

/** Обновить пару токенов; null — сессия закончилась, нужен вход по коду. */
export async function refresh(): Promise<string | null> {
  const token = await refreshToken();
  if (!token) return null;
  const response = await backendJson("auth/refresh", { refresh_token: token });
  if (!response.ok) {
    await clearSession();
    return null;
  }
  const tokens = (await response.json()) as TokenPair;
  await saveTokens(tokens);
  return tokens.access_token;
}

export async function backendJson(path: string, body: unknown) {
  return fetch(`${API_URL}/api/v1/${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
}
