import { describe, expect, it } from "vitest";
import { keyToBytes, pushBlocker, type PushEnv } from "./push";

const ok: PushEnv = { secureContext: true, supported: true, ios: false, standalone: false, permission: "default" };

describe("pushBlocker", () => {
  it("allows push on a secure, supported browser", () => {
    expect(pushBlocker(ok)).toBeNull();
  });

  it("explains each reason push cannot be turned on", () => {
    expect(pushBlocker({ ...ok, secureContext: false })).toContain("https");
    expect(pushBlocker({ ...ok, ios: true })).toContain("экран «Домой»");
    expect(pushBlocker({ ...ok, ios: true, standalone: true })).toBeNull();
    expect(pushBlocker({ ...ok, supported: false })).toContain("не поддерживает");
    expect(pushBlocker({ ...ok, permission: "denied" })).toContain("запрещены");
  });
});

describe("keyToBytes", () => {
  it("decodes an unpadded base64url VAPID key", () => {
    // 65 байт: 0x04 и две координаты точки P-256 — так выглядит публичный ключ VAPID.
    const raw = Uint8Array.from({ length: 65 }, (_, i) => (i === 0 ? 4 : (i * 37) % 256));
    const b64url = Buffer.from(raw).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    expect(Array.from(keyToBytes(b64url))).toEqual(Array.from(raw));
  });
});
