/**
 * localStorage-backed persistence used ONLY as a stand-in for the
 * saved-searches / alerts / auth endpoints the backend doesn't implement
 * yet (see BLOCKERS.md). Not meant to survive a real backend integration
 * as-is -- once /saved-searches, /alerts, and /auth exist server-side,
 * lib/api.ts's try/catch fallbacks to this file simply stop firing.
 */
import { SEED_ALERTS, SEED_SAVED_SEARCHES } from "./fixtures";
import type { AlertSubscription, PermitSearchParams, SavedSearch } from "./types";
import type { AuthResult } from "./api";

const SAVED_SEARCHES_KEY = "ci_saved_searches_v1";
const ALERTS_KEY = "ci_alerts_v1";
const AUTH_KEY = "ci_auth_v1";

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function readJson<T>(key: string, fallback: T): T {
  if (!isBrowser()) return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeJson<T>(key: string, value: T): void {
  if (!isBrowser()) return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// ---------------------------------------------------------------------------
// Saved searches
// ---------------------------------------------------------------------------

export function listSavedSearches(): SavedSearch[] {
  return readJson(SAVED_SEARCHES_KEY, SEED_SAVED_SEARCHES);
}

export function createSavedSearch(name: string, params: PermitSearchParams): SavedSearch {
  const current = listSavedSearches();
  const created: SavedSearch = {
    id: uid("search"),
    name,
    params,
    created_at: new Date().toISOString(),
  };
  writeJson(SAVED_SEARCHES_KEY, [created, ...current]);
  return created;
}

export function deleteSavedSearch(id: string): void {
  const current = listSavedSearches();
  writeJson(SAVED_SEARCHES_KEY, current.filter((s) => s.id !== id));
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export function listAlerts(): AlertSubscription[] {
  return readJson(ALERTS_KEY, SEED_ALERTS);
}

export function createAlert(
  input: Omit<AlertSubscription, "id" | "created_at" | "is_active">
): AlertSubscription {
  const current = listAlerts();
  const created: AlertSubscription = {
    ...input,
    id: uid("alert"),
    created_at: new Date().toISOString(),
    is_active: true,
  };
  writeJson(ALERTS_KEY, [created, ...current]);
  return created;
}

export function deleteAlert(id: string): void {
  const current = listAlerts();
  writeJson(ALERTS_KEY, current.filter((a) => a.id !== id));
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export function getAuth(): AuthResult | null {
  return readJson<AuthResult | null>(AUTH_KEY, null);
}

export function setAuth(result: AuthResult): void {
  writeJson(AUTH_KEY, result);
}

export function clearAuth(): void {
  if (!isBrowser()) return;
  window.localStorage.removeItem(AUTH_KEY);
}
