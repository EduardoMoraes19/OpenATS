import { getSessionToken } from "./session";

type AppRole = "super_admin" | "hiring_manager" | "interviewer";

function decodeJwtPayload(token: string): Record<string, unknown> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("Malformed JWT");
  return JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
}

/**
 * This is a UX-layer gate only (avoids rendering privileged UI before the
 * first backend round-trip) - the real enforcement is the backend
 * re-checking the token's role claim (and its `tv` claim against the
 * user's current token_version) on every request. Not verifying the
 * signature here is deliberate for that reason: a forged token would just
 * get past this check and then be rejected by the backend anyway.
 */
export async function requireRole(required: AppRole): Promise<void> {
  const token = await getSessionToken();
  if (!token) throw new Error("Unauthorized");

  const payload = decodeJwtPayload(token);
  if (payload["role"] !== required) throw new Error("Forbidden");
}
