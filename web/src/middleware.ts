import { NextRequest, NextResponse } from "next/server"

const PUBLIC_PAGES = ["/login", "/register"]

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl

  // /api/* is proxied via next.config.ts rewrites (which forward Set-Cookie); skip auth check here
  if (pathname.startsWith("/api/")) return NextResponse.next()

  if (PUBLIC_PAGES.some((p) => pathname.startsWith(p))) return NextResponse.next()

  const session = req.cookies.get("auth")
  if (!session) {
    return NextResponse.redirect(new URL("/login", req.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
}
