// Прокси к API пациента: подставляет токен из httpOnly-cookie, при истёкшем — обновляет один раз.
import { NextResponse } from "next/server";
import { API_URL, accessToken, refresh } from "@/lib/server/session";

// Через этот прокси — только методы пациента (/me…) и публичный контент.
function allowed(target: string) {
  return target === "me" || target.startsWith("me/") || target.startsWith("content/");
}

async function forward(request: Request, path: string[]) {
  const target = path.join("/");
  if (!allowed(target)) {
    return NextResponse.json({ detail: "Не найдено" }, { status: 404 });
  }
  const url = new URL(request.url);
  const body = request.method === "GET" ? undefined : await request.text();

  const call = (token: string | undefined) =>
    fetch(`${API_URL}/api/v1/${target}${url.search}`, {
      method: request.method,
      headers: {
        ...(token ? { authorization: `Bearer ${token}` } : {}),
        ...(body ? { "content-type": "application/json" } : {}),
      },
      body,
      cache: "no-store",
    });

  let response = await call(await accessToken());
  if (response.status === 401) {
    const renewed = await refresh();
    if (!renewed) return NextResponse.json({ detail: "Сессия завершена" }, { status: 401 });
    response = await call(renewed);
  }
  const headers = new Headers({ "cache-control": "no-store" });
  const type = response.headers.get("content-type");
  if (type) headers.set("content-type", type);
  return new NextResponse(response.status === 204 ? null : await response.arrayBuffer(), {
    status: response.status,
    headers,
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, { params }: Context) {
  return forward(request, (await params).path);
}

export async function POST(request: Request, { params }: Context) {
  return forward(request, (await params).path);
}

export async function PUT(request: Request, { params }: Context) {
  return forward(request, (await params).path);
}
