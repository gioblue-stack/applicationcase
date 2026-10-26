// Только сервер: токены врача живут в httpOnly-cookie и в браузерный JavaScript не попадают.
import "server-only";
import { cookies } from "next/headers";

export const API_URL = process.env.MC_API_URL ?? "http://127.0.0.1:8000";

const ACCESS = "mc_access";
const REFRESH = "mc_refresh";
const MFA = "mc_mfa";

type TokenPair = { access_token: string; refresh_token: string; access_expires_at: string; refresh_expires_at: string };

function cookieOptions(expires: Date) {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires,
  };
}

export async function saveTokens(tokens: TokenPair) {
  const jar = await cookies();
  jar.set(ACCESS, tokens.access_token, cookieOptions(new Date(tokens.access_expires_at)));
  jar.set(REFRESH, tokens.refresh_token, cookieOptions(new Date(tokens.refresh_expires_at)));
  jar.delete(MFA);
}

export async function clearSession() {
  const jar = await cookies();
  for (const name of [ACCESS, REFRESH, MFA]) jar.delete(name);
}

export async function saveMfaToken(token: string) {
  (await cookies()).set(MFA, token, cookieOptions(new Date(Date.now() + 5 * 60_000)));
}

export async function mfaToken(): Promise<string | undefined> {
  return (await cookies()).get(MFA)?.value;
}

export async function accessToken(): Promise<string | undefined> {
  return (await cookies()).get(ACCESS)?.value;
}

export async function refreshToken(): Promise<string | undefined> {
  return (await cookies()).get(REFRESH)?.value;
}

/** Обновить пару токенов. Сессия врача закрывается после 30 минут бездействия (§5.6) — тогда null. */
export async function refresh(): Promise<string | null> {
  const token = await refreshToken();
  if (!token) return null;
  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refresh_token: token }),
    cache: "no-store",
  });
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
