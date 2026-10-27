// Без сессии страницы ведут на вход. Экран помощи открывается всегда — и без входа (§5.5).
import { NextResponse, type NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  if (!request.cookies.has("mcp_refresh")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|help|api|_next|manifest.webmanifest|sw.js|icons|favicon.ico).*)"],
};
