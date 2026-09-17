/**
 * The explorer's API surface.
 *
 * `search` posts rather than gets, because the advanced builder's condition
 * tree does not fit in a query string. The GET form still exists on the
 * backend (`/client/records`) and is what a pasted, bookmarked URL uses.
 */

import { api, download } from "@/api/client";
import type { RecordDetail, RecordPage, RecordQuery, Related } from "@/api/types";

/**
 * Drop keys with no value before the body goes out.
 *
 * Flask-RESTX validates every request body against the model the endpoint
 * declares, and a `dict` field in that model is typed `object` — so an explicit
 * `"condition_tree": null` is rejected with a 400 ("None is not of type
 * 'object'") where *omitting* the key is accepted. Since a null and an absent
 * key mean exactly the same thing to the backend, the client sends the shape
 * that cannot fail.
 */
export function compact<T extends object>(body: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(body).filter(([, value]) => value !== null && value !== undefined),
  ) as Partial<T>;
}

export const recordsApi = {
  search: (query: RecordQuery, signal?: AbortSignal) =>
    api.post<RecordPage>("/client/records/search", compact(query), { signal }),

  detail: (id: string, signal?: AbortSignal) =>
    api.get<RecordDetail>(`/client/records/${encodeURIComponent(id)}`, { signal }),

  related: (id: string, signal?: AbortSignal) =>
    api.get<Related>(`/client/records/${encodeURIComponent(id)}/related`, { signal }),

  export: (query: RecordQuery & { format: string }) =>
    download("/client/records/export", {
      method: "POST",
      body: compact(query),
      fallbackName: `video-records.${query.format}`,
    }),
};
