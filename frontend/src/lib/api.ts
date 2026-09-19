import type { ApiProfile, Health, RouteResponse } from "./types";

// Requests go to /api/*, which next.config.ts rewrites to the FastAPI backend (BACKEND_URL).

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// FastAPI sends `detail` as a string for HTTPException and as a list for request-validation errors.
function detailMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d as { msg?: string }).msg)
      .filter(Boolean)
      .join("; ");
  }
  return fallback;
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal, headers: { accept: "application/json" } });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // Not JSON: the proxy answers 5xx with plain text when the backend is down.
    }
    throw new ApiError(res.status, detailMessage(body, res.statusText || `HTTP ${res.status}`));
  }
  return res.json() as Promise<T>;
}

/** GET /api/health */
export function getHealth(signal?: AbortSignal): Promise<Health> {
  return request<Health>("/api/health", signal);
}

/** GET /api/profiles */
export function getProfiles(signal?: AbortSignal): Promise<ApiProfile[]> {
  return request<ApiProfile[]>("/api/profiles", signal);
}

export interface RouteParams {
  from: { lat: number; lon: number };
  to: { lat: number; lon: number };
  profile: string;
  allowUnverifiedCrossings: boolean;
}

/** GET /api/route */
export function getRoute(params: RouteParams, signal?: AbortSignal): Promise<RouteResponse> {
  const q = new URLSearchParams({
    from_lat: String(params.from.lat),
    from_lon: String(params.from.lon),
    to_lat: String(params.to.lat),
    to_lon: String(params.to.lon),
    profile: params.profile,
    allow_unverified_crossings: String(params.allowUnverifiedCrossings),
  });
  return request<RouteResponse>(`/api/route?${q}`, signal);
}

/** A message a person can act on, for any failure from the endpoints above. */
export function describeError(err: unknown): { message: string; status: number | null } {
  if (err instanceof ApiError) {
    if (err.status >= 500 && err.status !== 503) {
      return { message: "The routing service isn't reachable. Is the backend running?", status: err.status };
    }
    return { message: err.message, status: err.status };
  }
  return { message: "Couldn't reach the server.", status: null };
}
