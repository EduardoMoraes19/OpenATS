import "server-only";

import { cookies } from "next/headers";

/**
 * Self-hosted JWT session, replacing the Asgardeo-managed session this app
 * used to rely on. The backend issues the JWT (see backend-py's
 * app/shared/auth/jwt_auth.py); this app only stores and forwards it.
 *
 * The token itself IS the session - no server-side session store - so an
 * httpOnly cookie holding the raw JWT is enough. httpOnly keeps it out of
 * reach of any client-side JS (XSS protection); the one deliberate
 * exception is /api/session-token, which hands the raw token to the
 * browser for the Socket.IO handshake (a WebSocket connecting directly to
 * the backend, which Next can't proxy transparently).
 */
export const SESSION_COOKIE = "openats_session";

export async function getSessionToken(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value;
}

export async function setSessionCookie(token: string): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    // Matches the backend's ACCESS_TOKEN_EXPIRE_MINUTES default (30m) plus
    // a little slack - the cookie outliving the token is harmless (the
    // backend still rejects an expired one), only the reverse would be a
    // problem.
    maxAge: 60 * 60,
  });
}

export async function clearSessionCookie(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
}
