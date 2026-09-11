import { NextResponse } from "next/server";
import { getSessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

// Gives the browser the current session token for the socket handshake -
// the one deliberate exception to the session cookie being httpOnly (see
// lib/session.ts), since Socket.IO opens a WebSocket straight to the
// backend, which Next can't proxy transparently the way it does HTTP.
export async function GET() {
  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ token: null }, { status: 401 });
  }

  return NextResponse.json(
    { token },
    { headers: { "Cache-Control": "no-store" } },
  );
}
