// VentureGPS V2 Capital Intelligence API transport.
//
// Deliberately a SEPARATE fetch function from lib/api/client.ts's apiFetch, not a reuse of it: apiFetch throws a
// single generic Error whose status code is only embedded in the message text (`/\(\d+\)/`), which every existing
// caller matches with a regex (see app/startup/[id]/page.tsx's own isNotFoundError). The V2 API needs to
// distinguish 404 / 400 / 422 / 503 as first-class states (unknown market vs. insufficient query vs. the
// database being down -- see docs/v2/CAPITAL_API.md's error table), so this throws a typed V2ApiError carrying
// the real `status` instead of asking every call site to parse a message string. The BASE URL resolution
// (NEXT_PUBLIC_API_URL) is identical to apiFetch's own -- V2's routes are mounted on the same FastAPI process
// (app/api.py's `app.include_router(v2_capital_router)`), so no new environment variable is introduced for this.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const V2_PREFIX = "/api/v2";

export class V2ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "V2ApiError";
    this.status = status;
  }
}

export function isV2NotFound(error: unknown): boolean {
  return error instanceof V2ApiError && error.status === 404;
}

export function isV2ServiceUnavailable(error: unknown): boolean {
  return error instanceof V2ApiError && error.status === 503;
}

type Query = Record<string, string | number | undefined>;

function buildQueryString(query?: Query): string {
  if (!query) return "";

  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
      params.set(key, String(value));
    }
  }

  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

// A short, request-scoped timeout: this backs a public, unauthenticated page (no signed-in user waiting on a
// slow founder workflow) -- a hung database connection should fail fast into the 503/error state rather than
// leave a visitor's browser spinning indefinitely.
const DEFAULT_TIMEOUT_MS = 10_000;

export async function v2Fetch<T>(path: string, query?: Query, revalidateSeconds?: number): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${V2_PREFIX}${path}${buildQueryString(query)}`, {
      method: "GET",
      signal: controller.signal,
      // Follows this app's own caching convention (see lib/api/8, "Prefer server-side initial data fetching"):
      // no cache directive by default, so plain calls behave exactly as before. A caller that DOES want Next's
      // Data Cache (e.g. the public /markets/[slug] route, where a market's Capital Signal is safe to reuse for a
      // few minutes across visitors) opts in explicitly with `revalidateSeconds` -- this transport never decides
      // that for every V2 endpoint at once.
      ...(revalidateSeconds !== undefined ? { next: { revalidate: revalidateSeconds } } : {}),
    });
  } catch {
    if (controller.signal.aborted) {
      throw new V2ApiError(503, `Request timed out: ${path}`);
    }

    throw new V2ApiError(503, `Network error reaching the Capital Intelligence API: ${path}`);
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let detail = "";

    try {
      const data = (await response.json()) as { detail?: unknown };
      detail = typeof data?.detail === "string" ? data.detail : "";
    } catch {
      // Not JSON, or no body -- fine, fall back to a generic message below. Never surfaces raw response text
      // (which could be an HTML error page, a stack trace, etc.) to the caller.
    }

    throw new V2ApiError(response.status, detail || `Capital Intelligence API request failed (${response.status}): ${path}`);
  }

  // response.json() parses JSON strings as JS strings, never as numbers -- the exactness guarantee for
  // minor_units/numerator/denominator (see types/v2/capital.ts) holds automatically as long as every caller's
  // type annotation keeps those fields typed `string`. No custom JSON reviver is needed or used.
  return response.json() as Promise<T>;
}
