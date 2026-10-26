// Первичная настройка приложения-аутентификатора: секрет и QR-код (QR рисуется на сервере).
import { NextResponse } from "next/server";
import QRCode from "qrcode";
import { backendJson, mfaToken } from "@/lib/server/session";

export async function POST() {
  const token = await mfaToken();
  if (!token) return NextResponse.json({ detail: "Начните вход заново" }, { status: 401 });
  const response = await backendJson("auth/doctor/totp/setup", { mfa_token: token });
  const data = await response.json();
  if (!response.ok) return NextResponse.json(data, { status: response.status });
  const qr = await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 220 });
  return NextResponse.json({ secret: data.secret, qr });
}
