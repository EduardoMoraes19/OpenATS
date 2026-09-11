"use client";

import { createContext, useContext } from "react";

/**
 * Carries the session token from the dashboard layout (a server component,
 * where the httpOnly session cookie lives - see lib/session.ts) down to the
 * client hooks that open socket connections. The backend rejects sockets
 * without it.
 */
const SocketTokenContext = createContext<string | undefined>(undefined);

export function SocketAuthProvider({
  token,
  children,
}: {
  token: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <SocketTokenContext.Provider value={token}>
      {children}
    </SocketTokenContext.Provider>
  );
}

export function useSocketToken(): string | undefined {
  return useContext(SocketTokenContext);
}
