// Запрос одноразового кода на телефон или e-mail.
import { NextResponse } from "next/server";
import { backendJson } from "@/lib/server/session";

export async function POST(request: Request) {
  const { login } = await request.json();
  const response = await backendJson("auth/code", { login });
  return NextResponse.json(await response.json(), { status: response.status });
}
