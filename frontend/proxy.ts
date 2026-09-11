import { NextResponse, type NextRequest } from "next/server";

// Deliberately NOT imported from lib/session.ts: that module pulls in
// next/headers (RSC-only) and is marked "server-only", neither of which is
// safe inside Edge middleware. Keep this literal in sync with
// lib/session.ts's SESSION_COOKIE.
const SESSION_COOKIE = "openats_session";

/**
 * Route protection based on the presence of the session cookie only -
 * signature/expiry are always re-checked by the backend on the actual data
 * request (see lib/auth-action.ts), so a stale-but-present cookie just
 * means the first real fetch on the page 401s rather than the middleware
 * catching it a step earlier. That's an acceptable tradeoff for keeping
 * the Edge middleware dependency-free.
 */
function isPublicRoute(pathname: string): boolean {
  return (
    pathname === "/login" ||
    pathname.startsWith("/careers") ||
    pathname.startsWith("/assessment/") ||
    pathname.startsWith("/interview/") ||
    pathname.startsWith("/offer/") ||
    pathname.startsWith("/api/public/") ||
    pathname.startsWith("/api/auth/")
  );
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

  if (pathname === "/login" && hasSession) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  if (!isPublicRoute(pathname) && !hasSession) {
    const signInUrl = new URL("/login", request.url);
    return NextResponse.redirect(signInUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
