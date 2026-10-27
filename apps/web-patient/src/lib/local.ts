// Хранилище на устройстве. Только то, что нужно экрану помощи без сети, и очередь неотправленных нажатий кнопки.
"use client";

import type { Contact } from "./types";

export function readLocal<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null; // приватный режим или хранилище отключено — экран помощи всё равно покажет 112
  }
}

export function writeLocal(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

/** Что экрану помощи нужно знать о пациенте без сети: регион (телефоны), есть ли врач, близкие из плана. */
export type HelpProfile = { region: string | null; hasDoctor: boolean; contacts: Contact[] };
export const HELP_PROFILE = "mc_help_profile";

export function helpProfile(): HelpProfile {
  return readLocal<HelpProfile>(HELP_PROFILE) ?? { region: null, hasDoctor: false, contacts: [] };
}

export function saveHelpProfile(patch: Partial<HelpProfile>) {
  writeLocal(HELP_PROFILE, { ...helpProfile(), ...patch });
}

// --- «Мне сейчас очень плохо»: экран помощи открывается сразу, сигнал врачу уходит, когда есть сеть ---

type PanicPress = { client_id: string; pressed_at: string };
const PANIC_OUTBOX = "mc_panic_outbox";

export function queuePanic(press: PanicPress) {
  writeLocal(PANIC_OUTBOX, [...(readLocal<PanicPress[]>(PANIC_OUTBOX) ?? []), press]);
}

/** Отправить накопленные нажатия. true — врач получил сигнал хотя бы по одному из них. */
export async function flushPanic(): Promise<boolean> {
  const queue = readLocal<PanicPress[]>(PANIC_OUTBOX) ?? [];
  const left: PanicPress[] = [];
  let delivered = false;
  for (const press of queue) {
    try {
      const response = await fetch("/api/backend/me/panic-events", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(press),
      });
      if (response.ok) delivered = true;
      // 401 — пациент не вошёл: сигнал некому адресовать, но телефоны помощи он уже видит.
      else if (response.status >= 500) left.push(press);
    } catch {
      left.push(press); // нет сети — повторим при следующем открытии сайта
    }
  }
  writeLocal(PANIC_OUTBOX, left.length ? left : null);
  return delivered;
}
