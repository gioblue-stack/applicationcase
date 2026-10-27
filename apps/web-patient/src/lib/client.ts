// Браузер ходит только в свой BFF (/api/backend/…); токены подставляет сервер Next.js.
"use client";

export class ApiError extends Error {
  constructor(public status: number, message: string, public data: unknown = null) {
    super(message);
  }
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, {
    method: init?.method ?? "GET",
    headers: init?.body !== undefined ? { "content-type": "application/json" } : undefined,
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    cache: "no-store",
  });
  if (response.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "Сессия завершена");
  }
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, detailText(data), data);
  return data as T;
}

function detailText(data: unknown): string {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "Проверьте ответы и попробуйте ещё раз";
  return "Не получилось отправить. Попробуйте ещё раз";
}

/** UUID для client_id. crypto.randomUUID есть только на https, а с телефона в локальной сети сайт открыт по http. */
export function newId(): string {
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export function nowIso(): string {
  return new Date().toISOString();
}
