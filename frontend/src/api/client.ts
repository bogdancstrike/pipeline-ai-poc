/**
 * The HTTP client every request goes through.
 *
 * Three things it guarantees, so no caller has to:
 *
 * 1. **A correlation id on every request**, echoed back by the server and
 *    attached to any error. A screenshot of a failure carrying the id is a
 *    failure somebody can find in the logs.
 * 2. **Domain errors as `ApiError`.** The backend answers every failure with
 *    `{error, message, details?}` (see `src/client/errors.py`), so a screen
 *    can ask "was this a 503 because the database is down?" rather than
 *    parsing bodies itself.
 * 3. **Cancellation.** Every call takes a signal, because a filter that fires
 *    on each keystroke will otherwise render the answer to a question the user
 *    has already stopped asking.
 */

import { API_PREFIX, CORRELATION_HEADER } from "@/config";
import { asText } from "@/lib/text";

export interface ApiErrorBody {
  error: string;
  message: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly correlationId: string;

  constructor(status: number, body: ApiErrorBody, correlationId: string) {
    super(body.message || body.error || `Request failed with ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error || "error";
    this.details = body.details ?? {};
    this.correlationId = correlationId;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** The records database is down or turned off — the shell says so once. */
  get isUnavailable(): boolean {
    return this.status === 503;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** Serialised into the query string; `undefined` and `""` are dropped. */
  params?: Record<string, unknown>;
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function newCorrelationId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return Math.random().toString(16).slice(2).padEnd(32, "0");
}

export function buildQuery(params: Record<string, unknown> | undefined): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      // The API reads a repeated value as a comma-separated list, which is
      // what `client/query.py` splits on.
      const joined = value.filter((v) => v !== undefined && v !== null && v !== "").join(",");
      if (joined) search.set(key, joined);
    } else {
      search.set(key, asText(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/** The correlation id of the most recent failure, for a support ticket. */
let lastFailure: string | null = null;

export function lastFailedCorrelationId(): string | null {
  return lastFailure;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", params, body, signal, headers = {} } = options;
  const correlationId = newCorrelationId();

  const response = await fetch(`${API_PREFIX}${path}${buildQuery(params)}`, {
    method,
    signal,
    headers: {
      Accept: "application/json",
      [CORRELATION_HEADER]: correlationId,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...headers,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

  const echoed = response.headers.get(CORRELATION_HEADER) ?? correlationId;
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const parsed: unknown = text ? safeParse(text) : null;

  if (!response.ok) {
    lastFailure = echoed;
    throw new ApiError(response.status, asErrorBody(parsed, response.status), echoed);
  }
  return parsed as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { error: "invalid_response", message: text.slice(0, 300) };
  }
}

function asErrorBody(parsed: unknown, status: number): ApiErrorBody {
  if (parsed && typeof parsed === "object" && "error" in parsed) {
    return parsed as ApiErrorBody;
  }
  return { error: "error", message: `Request failed with ${status}` };
}

/**
 * Fetch a file and hand it to the browser to save.
 *
 * The filename comes from the server's `Content-Disposition`, because the
 * server is what knows the format and the moment — a client that names the
 * file itself eventually disagrees with the file's contents.
 */
export async function download(
  path: string,
  options: RequestOptions & { fallbackName?: string } = {},
): Promise<void> {
  const { method = "POST", params, body, signal, fallbackName = "export" } = options;
  const correlationId = newCorrelationId();

  const response = await fetch(`${API_PREFIX}${path}${buildQuery(params)}`, {
    method,
    signal,
    headers: {
      [CORRELATION_HEADER]: correlationId,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

  const echoed = response.headers.get(CORRELATION_HEADER) ?? correlationId;
  if (!response.ok) {
    // A failed download still answers with the JSON error envelope, so the
    // caller gets the same `ApiError` rather than a saved file containing an
    // error message.
    const text = await response.text();
    throw new ApiError(response.status, asErrorBody(safeParse(text), response.status), echoed);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filenameFrom(response.headers.get("Content-Disposition")) ?? fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoked on the next tick: revoking synchronously races the click in some
  // browsers and saves a zero-byte file.
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function filenameFrom(header: string | null): string | undefined {
  if (!header) return undefined;
  const quoted = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
  return quoted?.[1] ? decodeURIComponent(quoted[1]) : undefined;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
