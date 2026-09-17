/**
 * Build-time constants. Deliberately almost empty.
 *
 * The API lives on the same origin as the bundle — nginx proxies `/client` to
 * the pipeline container, and `vite dev` proxies it to localhost:5696 — so
 * there is no API URL to configure and none compiled in. An environment
 * variable baked into a bundle is a bundle you have to rebuild to move.
 */

/** Everything the client app reads lives under this prefix. */
export const API_PREFIX = "";

export const CORRELATION_HEADER = "X-Correlation-ID";

/** localStorage keys, namespaced so two apps on one origin cannot collide. */
export const STORAGE_KEYS = {
  appearance: "video.appearance",
  density: "video.density",
  sidebarCollapsed: "video.sidebar.collapsed",
  recentSearches: "video.search.recent",
  owner: "video.owner",
} as const;

/** How many recent searches the search box offers. */
export const RECENT_SEARCH_LIMIT = 8;
