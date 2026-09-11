"use server";

import { redirect } from "next/navigation";
import { clearSessionCookie, getSessionToken, setSessionCookie } from "@/lib/session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export type LoginState = { error?: string } | undefined;

export async function loginAction(
  _prevState: LoginState,
  formData: FormData,
): Promise<LoginState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!email || !password) {
    return { error: "Email and password are required." };
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return { error: "Could not reach the server. Please try again." };
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "Login failed" }));
    return { error: (body as { error?: string }).error ?? "Invalid email or password." };
  }

  const body = (await res.json()) as { data: { accessToken: string } };
  await setSessionCookie(body.data.accessToken);
  redirect("/");
}

export async function logoutAction(): Promise<void> {
  const token = await getSessionToken();
  if (token) {
    try {
      await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
    } catch {
      // Best-effort - the cookie still gets cleared below regardless, so
      // the user is locally signed out even if the backend call failed.
    }
  }
  await clearSessionCookie();
  redirect("/login");
}
