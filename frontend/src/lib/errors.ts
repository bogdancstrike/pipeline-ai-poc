/**
 * One failure, one sentence — in one place.
 *
 * Every screen that catches an error asks this for the words, so a reader gets
 * the same sentence for the same failure wherever they hit it, and every
 * sentence that can carry a correlation id does.
 *
 * The case worth naming here is 503: this app's database is a *separate*
 * service from the pipeline that fills it, so "the records database is
 * unavailable" is a thing a reader can act on — the pipeline may still be
 * analysing videos perfectly well.
 */

import { ApiError } from "@/api/client";

export interface ErrorTextOptions {
  /** Shown when the failure is not one the API described. */
  fallback?: string;
  /** The verb a refusal should name — "export these records". */
  action?: string;
}

export function errorText(
  error: unknown,
  { fallback = "Something went wrong.", action = "do that" }: ErrorTextOptions = {},
): string {
  if (error instanceof ApiError) {
    if (error.isUnavailable) {
      return `The records database is unavailable, so the app cannot ${action}. The pipeline itself may be unaffected — records are still written to output/.`;
    }
    if (error.isNotFound) {
      return error.message;
    }
    return `${error.message} · ${error.correlationId}`;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

/** True when the failure is the database being down rather than a bad request. */
export function isUnavailable(error: unknown): boolean {
  return error instanceof ApiError && error.isUnavailable;
}
