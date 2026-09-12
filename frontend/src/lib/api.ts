import type {
  BustCacheResult,
  HealthStatus,
  Metrics,
  QueryPayload,
  QueryResult,
} from "./types";

/**
 * API base. Defaults to a same-origin `/api` path, which Next.js rewrites to
 * the FastAPI backend during development (see `next.config.mjs`). Point
 * NEXT_PUBLIC_API_BASE at the backend origin for direct network access.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

const DEFAULTS: RequestInit = {
  headers: { "Content-Type": "application/json" },
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = init?.method ? `${API_BASE}${path}` : `${API_BASE}${path}`;
  const response = await fetch(url, { ...DEFAULTS, ...init });

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body: unknown = await response.json();
      if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        (typeof body.detail === "string" || Array.isArray(body.detail))
      ) {
        detail = String(
          Array.isArray(body.detail)
            ? body.detail.map((d) => d?.msg ?? "").join("; ")
            : body.detail
        );
      }
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const runRawQuery = (payload: QueryPayload): Promise<QueryResult> =>
  request("/query/raw", { method: "POST", body: JSON.stringify(payload) });

export const runWarmstart = (payload: QueryPayload): Promise<QueryResult> =>
  request("/query/warmstart", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const bustCache = (
  system_prompt_version: string
): Promise<BustCacheResult> =>
  request("/admin/bust-cache", {
    method: "POST",
    body: JSON.stringify({ system_prompt_version }),
  });

export const getMetrics = (): Promise<Metrics> => request("/metrics");

export const getHealth = (): Promise<HealthStatus> => request("/health");