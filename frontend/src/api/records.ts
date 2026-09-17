/**
 * The explorer's API surface.
 *
 * `search` posts rather than gets, because the advanced builder's condition
 * tree does not fit in a query string. The GET form still exists on the
 * backend (`/client/records`) and is what a pasted, bookmarked URL uses.
 */

import { api, download } from "@/api/client";
import type { RecordDetail, RecordPage, RecordQuery, Related } from "@/api/types";

export const recordsApi = {
  search: (query: RecordQuery, signal?: AbortSignal) =>
    api.post<RecordPage>("/client/records/search", query, { signal }),

  detail: (id: string, signal?: AbortSignal) =>
    api.get<RecordDetail>(`/client/records/${encodeURIComponent(id)}`, { signal }),

  related: (id: string, signal?: AbortSignal) =>
    api.get<Related>(`/client/records/${encodeURIComponent(id)}/related`, { signal }),

  export: (query: RecordQuery & { format: string }) =>
    download("/client/records/export", {
      method: "POST",
      body: query,
      fallbackName: `video-records.${query.format}`,
    }),
};
