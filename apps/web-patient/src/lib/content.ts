// Публичный контент (опросники, тексты, телефоны) кэшируется на устройстве: экран помощи работает без сети.
"use client";

import { useEffect, useState } from "react";
import { readLocal, writeLocal } from "./local";
import type { Bootstrap } from "./types";

const KEY = "mc_bootstrap_v1";

export function useContent(): Bootstrap | null {
  const [content, setContent] = useState<Bootstrap | null>(null);
  useEffect(() => {
    setContent(readLocal<Bootstrap>(KEY));
    fetch("/api/backend/content/bootstrap")
      .then((r) => (r.ok ? r.json() : null))
      .then((fresh: Bootstrap | null) => {
        if (!fresh) return;
        setContent(fresh);
        writeLocal(KEY, fresh);
      })
      .catch(() => null); // без сети — версия с устройства
  }, []);
  return content;
}
