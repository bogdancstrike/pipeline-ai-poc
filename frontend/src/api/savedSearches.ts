import { api } from "@/api/client";
import type { RecordPage, RecordQuery, SavedSearch, SavedSearchPage } from "@/api/types";

export interface SavedSearchInput {
  name: string;
  description?: string;
  owner?: string;
  pinned?: boolean;
  payload: RecordQuery;
}

export const savedSearchApi = {
  list: (params: { q?: string; owner?: string; page_size?: number } = {}, signal?: AbortSignal) =>
    api.get<SavedSearchPage>("/client/searches", { params: { ...params }, signal }),

  create: (body: SavedSearchInput) => api.post<SavedSearch>("/client/searches", body),

  update: (id: string, body: Partial<SavedSearchInput>) =>
    api.put<SavedSearch>(`/client/searches/${encodeURIComponent(id)}`, body),

  remove: (id: string) => api.delete<{ deleted: string }>(`/client/searches/${encodeURIComponent(id)}`),

  /** Run it, and count the run — what makes "recently used" honest. */
  run: (id: string, overrides: RecordQuery = {}) =>
    api.post<RecordPage>(`/client/searches/${encodeURIComponent(id)}/run`, overrides),
};
