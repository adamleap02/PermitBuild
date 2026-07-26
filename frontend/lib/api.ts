/**
 * Thin typed client for the backend/ FastAPI service.
 *
 * Contract implemented today by the backend (see backend/app/routers/):
 *   GET /permits            (jurisdiction_id, permit_type, status, date_from,
 *                             date_to, min_value, max_value, keyword, page, page_size)
 *   GET /permits/{id}
 *   GET /properties/{id}
 *   GET /export             (same filters, returns a CSV file)
 *   GET /jurisdictions
 *
 * The product spec (and the filter sidebar in components/search/) also
 * calls for city/county/zip/radius/contractor/builder/architect/
 * owner_occupied/property_type filters. Those query params are sent to
 * `/permits` here on the assumption the backend will grow to accept them
 * (FastAPI ignores undeclared query params rather than erroring, so this is
 * forward-compatible today) -- see BLOCKERS.md for exactly which filters
 * are live server-side right now vs. only honored by the mock fallback.
 *
 * Every function here:
 *   1. Uses NEXT_PUBLIC_USE_MOCKS=true to force the local fixtures, OR
 *   2. Tries the real API first and falls back to fixtures automatically
 *      if the request fails (backend not running, network error, etc.)
 * ...so the UI is always demonstrable, whether or not the backend is up.
 */
import {
  getPermitMock,
  getPropertyMock,
  listJurisdictionsMock,
  searchPermitsMock,
} from "./fixtures";
import type {
  AlertSubscription,
  JurisdictionOut,
  PermitDetail,
  PermitListResponse,
  PermitSearchParams,
  PropertyOut,
  SavedSearch,
} from "./types";
import * as localStore from "./local-store";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const FORCE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON; keep statusText
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

function buildQuery(params: Record<string, unknown>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === "any") continue;
    qs.set(key, String(value));
  }
  return qs.toString();
}

function warnFallback(what: string, err: unknown) {
  // eslint-disable-next-line no-console
  console.warn(
    `[api] ${what} request to ${API_URL} failed, falling back to local fixtures. ` +
      `Start the backend (see ../backend/README or root README) to use live data.`,
    err
  );
}

// ---------------------------------------------------------------------------
// Permits
// ---------------------------------------------------------------------------

export async function searchPermits(params: PermitSearchParams): Promise<PermitListResponse> {
  if (FORCE_MOCKS) return searchPermitsMock(params);
  try {
    const qs = buildQuery(params as Record<string, unknown>);
    return await request<PermitListResponse>(`/permits?${qs}`);
  } catch (err) {
    warnFallback("GET /permits", err);
    return searchPermitsMock(params);
  }
}

export async function getPermit(id: number): Promise<PermitDetail> {
  if (FORCE_MOCKS) {
    const permit = getPermitMock(id);
    if (!permit) throw new ApiError("Permit not found", 404);
    return permit;
  }
  try {
    return await request<PermitDetail>(`/permits/${id}`);
  } catch (err) {
    const permit = getPermitMock(id);
    if (permit) {
      warnFallback(`GET /permits/${id}`, err);
      return permit;
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Properties
// ---------------------------------------------------------------------------

export async function getProperty(id: number): Promise<PropertyOut> {
  if (FORCE_MOCKS) {
    const property = getPropertyMock(id);
    if (!property) throw new ApiError("Property not found", 404);
    return property;
  }
  try {
    return await request<PropertyOut>(`/properties/${id}`);
  } catch (err) {
    const property = getPropertyMock(id);
    if (property) {
      warnFallback(`GET /properties/${id}`, err);
      return property;
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Jurisdictions
// ---------------------------------------------------------------------------

export async function listJurisdictions(): Promise<JurisdictionOut[]> {
  if (FORCE_MOCKS) return listJurisdictionsMock();
  try {
    return await request<JurisdictionOut[]>(`/jurisdictions`);
  } catch (err) {
    warnFallback("GET /jurisdictions", err);
    return listJurisdictionsMock();
  }
}

// ---------------------------------------------------------------------------
// Export -- the backend streams a CSV; there's nothing to fall back to in
// mock mode besides pointing at the same querystring (the browser will just
// download whatever the backend/mock endpoint returns). We build the URL
// only; the caller triggers the download via a plain <a href> or
// window.location so the browser handles the streamed response natively.
// ---------------------------------------------------------------------------

export function buildExportUrl(params: PermitSearchParams): string {
  const qs = buildQuery(params as Record<string, unknown>);
  return `${API_URL}/export?${qs}`;
}

// ---------------------------------------------------------------------------
// Saved searches / Alerts / Auth -- UI-only stubs. The backend does not
// implement these endpoints yet (no /saved-searches, /alerts, or /auth
// router in backend/app/main.py as of this writing -- see BLOCKERS.md).
// Each function still attempts the real endpoint first (so this file needs
// zero changes once the backend adds them) and falls back to a
// localStorage-backed store that simulates persistence for the demo.
// ---------------------------------------------------------------------------

export async function listSavedSearches(): Promise<SavedSearch[]> {
  try {
    return await request<SavedSearch[]>(`/saved-searches`);
  } catch (err) {
    warnFallback("GET /saved-searches (not implemented by backend yet)", err);
    return localStore.listSavedSearches();
  }
}

export async function createSavedSearch(
  name: string,
  params: PermitSearchParams
): Promise<SavedSearch> {
  try {
    return await request<SavedSearch>(`/saved-searches`, {
      method: "POST",
      body: JSON.stringify({ name, params }),
    });
  } catch (err) {
    warnFallback("POST /saved-searches (not implemented by backend yet)", err);
    return localStore.createSavedSearch(name, params);
  }
}

export async function deleteSavedSearch(id: string): Promise<void> {
  try {
    await request<void>(`/saved-searches/${id}`, { method: "DELETE" });
  } catch (err) {
    warnFallback("DELETE /saved-searches (not implemented by backend yet)", err);
    localStore.deleteSavedSearch(id);
  }
}

export async function listAlerts(): Promise<AlertSubscription[]> {
  try {
    return await request<AlertSubscription[]>(`/alerts`);
  } catch (err) {
    warnFallback("GET /alerts (not implemented by backend yet)", err);
    return localStore.listAlerts();
  }
}

export async function createAlert(
  input: Omit<AlertSubscription, "id" | "created_at" | "is_active">
): Promise<AlertSubscription> {
  try {
    return await request<AlertSubscription>(`/alerts`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  } catch (err) {
    warnFallback("POST /alerts (not implemented by backend yet)", err);
    return localStore.createAlert(input);
  }
}

export async function deleteAlert(id: string): Promise<void> {
  try {
    await request<void>(`/alerts/${id}`, { method: "DELETE" });
  } catch (err) {
    warnFallback("DELETE /alerts (not implemented by backend yet)", err);
    localStore.deleteAlert(id);
  }
}

export interface AuthResult {
  user: { id: string; email: string; full_name: string | null; organization_name: string | null };
  token: string;
}

/**
 * Auth is a UI-only scaffold. There is no /auth router in the backend and
 * no real session/JWT handling here -- see BLOCKERS.md. This simulates a
 * successful login/signup and stores a fake token in localStorage purely
 * so the rest of the UI (e.g. a logged-in state in the navbar) has
 * something to react to. Do not treat this as real authentication.
 */
export async function loginStub(email: string, _password: string): Promise<AuthResult> {
  try {
    return await request<AuthResult>(`/auth/login`, {
      method: "POST",
      body: JSON.stringify({ email, password: _password }),
    });
  } catch (err) {
    warnFallback("POST /auth/login (not implemented -- stub only, see BLOCKERS.md)", err);
    const result: AuthResult = {
      user: { id: "stub-user", email, full_name: null, organization_name: null },
      token: "stub-token",
    };
    localStore.setAuth(result);
    return result;
  }
}

export async function signupStub(
  email: string,
  _password: string,
  fullName: string,
  organizationName: string
): Promise<AuthResult> {
  try {
    return await request<AuthResult>(`/auth/signup`, {
      method: "POST",
      body: JSON.stringify({ email, password: _password, full_name: fullName, organization_name: organizationName }),
    });
  } catch (err) {
    warnFallback("POST /auth/signup (not implemented -- stub only, see BLOCKERS.md)", err);
    const result: AuthResult = {
      user: { id: "stub-user", email, full_name: fullName, organization_name: organizationName },
      token: "stub-token",
    };
    localStore.setAuth(result);
    return result;
  }
}

export function logoutStub(): void {
  localStore.clearAuth();
}

export function getStoredAuth(): AuthResult | null {
  return localStore.getAuth();
}
