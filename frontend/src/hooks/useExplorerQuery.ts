/**
 * The explorer's question, kept in the URL.
 *
 * A search somebody can paste to a colleague is worth more than a slightly
 * tidier component, so every narrowing — the text, the facet menus, the page,
 * the sort — lives in the query string. The one exception is the advanced
 * condition tree: it is nested JSON, it can be long, and a URL is a poor place
 * for it, so it is held in state and persisted only by a saved search.
 */

import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { RecordQuery } from "@/api/types";
import { EMPTY_FILTERS, type SimpleFilters } from "@/components/explorer/SearchBar";

export interface ExplorerState {
  filters: SimpleFilters;
  page: number;
  pageSize: number;
  sort: string;
  order: "asc" | "desc";
}

const LIST_KEYS = ["sentiment", "status", "model"] as const;

export function useExplorerQuery() {
  const [params, setParams] = useSearchParams();

  const state = useMemo<ExplorerState>(() => {
    const list = (key: string) => {
      const raw = params.get(key);
      return raw ? raw.split(",").filter(Boolean) : [];
    };
    return {
      filters: {
        ...EMPTY_FILTERS,
        q: params.get("q") ?? "",
        sentiment: list("sentiment"),
        status: list("status"),
        model: list("model"),
      },
      page: Number(params.get("page") ?? 1) || 1,
      pageSize: Number(params.get("page_size") ?? 25) || 25,
      sort: params.get("sort") ?? "analysed_at",
      order: (params.get("order") as "asc" | "desc") ?? "desc",
    };
  }, [params]);

  const update = useCallback(
    (next: Partial<ExplorerState>) => {
      const merged = { ...state, ...next };
      const search = new URLSearchParams();
      if (merged.filters.q) search.set("q", merged.filters.q);
      for (const key of LIST_KEYS) {
        const values = merged.filters[key];
        if (values.length) search.set(key, values.join(","));
      }
      // A narrowing that changed sends the reader back to page 1: staying on
      // page 7 of an answer that now has two pages shows an empty table.
      const narrowed = next.filters !== undefined;
      const page = narrowed ? 1 : merged.page;
      if (page > 1) search.set("page", String(page));
      if (merged.pageSize !== 25) search.set("page_size", String(merged.pageSize));
      if (merged.sort !== "analysed_at") search.set("sort", merged.sort);
      if (merged.order !== "desc") search.set("order", merged.order);
      setParams(search, { replace: true });
    },
    [state, setParams],
  );

  /** The state as the body `/client/records/search` expects. */
  const toQuery = useCallback(
    (extra: Partial<RecordQuery> = {}): RecordQuery => ({
      query_text: state.filters.q,
      filters: {
        ...(state.filters.sentiment.length ? { sentiment: state.filters.sentiment.join(",") } : {}),
        ...(state.filters.status.length ? { status: state.filters.status.join(",") } : {}),
        ...(state.filters.model.length ? { model: state.filters.model.join(",") } : {}),
      },
      page: state.page,
      page_size: state.pageSize,
      sort: state.sort,
      order: state.order,
      facets: true,
      ...extra,
    }),
    [state],
  );

  return { state, update, toQuery };
}
