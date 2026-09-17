import { api } from "@/api/client";
import type { Dashboard, Statistics } from "@/api/types";

export interface RangeParams {
  range?: string;
  from?: string;
  to?: string;
}

export const dashboardApi = {
  overview: (params: RangeParams, signal?: AbortSignal) =>
    api.get<Dashboard>("/client/dashboard", { params: { ...params }, signal }),

  statistics: (params: RangeParams, signal?: AbortSignal) =>
    api.get<Statistics>("/client/statistics", { params: { ...params }, signal }),
};
