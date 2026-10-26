// Браузер ходит только в свой BFF (/api/backend/…); токены подставляет сервер Next.js.
"use client";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
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
  if (!response.ok) {
    throw new ApiError(response.status, (data as { detail?: string } | null)?.detail ?? "Ошибка сервера");
  }
  return data as T;
}
