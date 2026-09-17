/**
 * The pipeline's own endpoints — the ones that existed before this client app.
 *
 * Two ways to run a video, and the difference matters:
 *
 *   * `analyze` publishes to `video.in` and returns immediately. The seven
 *     workers then run across Kafka, and the record appears in the explorer
 *     when W7 writes it — seconds to minutes later, depending on the video.
 *   * `runWorker` runs ONE worker inside the HTTP request and answers with what
 *     it produced. Nothing is published, nothing is stored, nothing downstream
 *     is triggered. It is the way to ask "what does :8823 say about this file?"
 *     without committing a record.
 */

import { api } from "@/api/client";

export interface WorkerSpec {
  worker: string;
  step: number | null;
  kind: string;
  topics_in: string[];
  topics_out: string[];
  runs_first: string[];
  mocked: Record<string, boolean>;
  run: string;
}

export interface AnalyzeRequest {
  path: string;
  id?: string;
  name?: string;
  options?: Record<string, unknown>;
}

export interface AnalyzeResponse {
  id: string;
  path: string;
  status?: string;
  topic?: string;
  [key: string]: unknown;
}

export interface RunWorkerRequest {
  path?: string;
  id?: string;
  /** false runs this worker alone, on `message`, instead of its upstream chain. */
  chain?: boolean;
  message?: Record<string, unknown>;
  options?: Record<string, unknown>;
  /** W7 only: write the record file (and the database row) as a real run would. */
  persist?: boolean;
}

export const pipelineApi = {
  analyze: (body: AnalyzeRequest) => api.post<AnalyzeResponse>("/pipeline/analyze", body),

  workers: (signal?: AbortSignal) =>
    api.get<{ workers: WorkerSpec[]; run: string; note: string }>("/workers/list", { signal }),

  runWorker: (worker: string, body: RunWorkerRequest) =>
    api.post<Record<string, unknown>>(`/workers/${encodeURIComponent(worker)}/run`, body),

  health: (signal?: AbortSignal) =>
    api.get<Record<string, unknown>>("/pipeline/health", { signal }),
};
