import { serverFetch } from "@/lib/auth-action";
import type { User } from "@/types";

export interface CreateUserPayload {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  role: "super_admin" | "hiring_manager" | "interviewer";
}

export interface UpdateUserPayload {
  firstName?: string;
  lastName?: string;
  role?: "super_admin" | "hiring_manager" | "interviewer";
}

export async function fetchUsers(): Promise<User[]> {
  const res = await serverFetch<{ data: User[] }>("/users");
  return res.data;
}

export async function createUser(payload: CreateUserPayload): Promise<User> {
  const res = await serverFetch<{ data: User }>("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res.data;
}

export async function updateUser(
  id: number,
  payload: UpdateUserPayload,
): Promise<User> {
  const res = await serverFetch<{ data: User }>(`/users/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return res.data;
}

export async function deleteUser(id: number): Promise<void> {
  await serverFetch(`/users/${id}`, { method: "DELETE" });
}
