/**
 * The three prompts W6 posts to :8825.
 *
 * The `.txt` files under `src/prompts/` are the wording that ships; a row in
 * the database overrides it. Saving here changes what the *next* video is
 * summarised with — there is no restart and no rebuild, which is the whole
 * point of the editor.
 */

import { api } from "@/api/client";

export interface PromptRow {
  name: "summary" | "entities" | "sentiment" | string;
  file: string;
  text: string;
  default_text: string;
  version: number;
  updated_by: string;
  updated_at: string | null;
  /** False means the file is still in use — nothing saved yet, or the switch is off. */
  from_db: boolean;
  /** True when the stored text differs from the wording that shipped. */
  modified: boolean;
}

export interface PromptListing {
  items: PromptRow[];
  from_db: boolean;
  dir: string;
}

export const promptsApi = {
  list: (signal?: AbortSignal) => api.get<PromptListing>("/client/prompts", { signal }),

  save: (name: string, text: string, updatedBy?: string) =>
    api.put<PromptRow>(`/client/prompts/${encodeURIComponent(name)}`, {
      text,
      ...(updatedBy ? { updated_by: updatedBy } : {}),
    }),

  reset: (name: string) =>
    api.post<PromptRow>(`/client/prompts/${encodeURIComponent(name)}/reset`),
};
