"use client";

import * as React from "react";

import { getStoredAuth, loginStub, logoutStub, signupStub, type AuthResult } from "@/lib/api";

/**
 * Client-side auth stub. See BLOCKERS.md: there is no real session/JWT
 * handling here, just a localStorage flag so the navbar/UI can reflect a
 * "logged in" state end-to-end. Swap for NextAuth.js (or similar) once the
 * backend has a real /auth implementation.
 */
export function useAuth() {
  const [auth, setAuthState] = React.useState<AuthResult | null>(null);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    setAuthState(getStoredAuth());
    setLoaded(true);
  }, []);

  const login = React.useCallback(async (email: string, password: string) => {
    const result = await loginStub(email, password);
    setAuthState(result);
    return result;
  }, []);

  const signup = React.useCallback(
    async (email: string, password: string, fullName: string, organizationName: string) => {
      const result = await signupStub(email, password, fullName, organizationName);
      setAuthState(result);
      return result;
    },
    []
  );

  const logout = React.useCallback(() => {
    logoutStub();
    setAuthState(null);
  }, []);

  return { user: auth?.user ?? null, loaded, login, signup, logout };
}
