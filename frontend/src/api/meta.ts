import { api } from "@/api/client";
import type { ClientHealth, Meta } from "@/api/types";

export const metaApi = {
  /** The field catalogue the query builder is generated from. */
  fields: (signal?: AbortSignal) => api.get<Meta>("/client/meta", { signal }),
  health: (signal?: AbortSignal) => api.get<ClientHealth>("/client/health", { signal }),
};
