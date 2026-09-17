/**
 * The shapes the API answers with.
 *
 * Mirrors `src/client/` on the backend: `FieldDescriptor` is what
 * `FieldSet.describe()` returns, `RecordPage` is `pagination.envelope`, and the
 * chart series are what `client/dashboard.py` builds. Kept in one file so a
 * change on the backend has one place to land.
 */

export type FieldKind =
  | "text"
  | "enum"
  | "bool"
  | "number"
  | "datetime"
  | "uuid"
  | "json"
  | "array";

export interface FieldDescriptor {
  name: string;
  label: string;
  kind: FieldKind;
  sortable: boolean;
  filterable: boolean;
  searchable: boolean;
  facet: boolean;
  operators: string[];
  choices: string[];
}

export interface Meta {
  fields: FieldDescriptor[];
  searchable: string[];
  facets: string[];
  sentiments: string[];
  statuses: string[];
  services: string[];
  ranges: string[];
  export_formats: string[];
  page_sizes: number[];
}

export interface FacetValue {
  value: string | number | boolean | null;
  count: number;
}

export interface RecordRow {
  id: string;
  name: string;
  sentiment: string;
  status: string;
  analysed_at: string | null;
  summary_preview?: string;
  [column: string]: unknown;
}

export interface RecordPage {
  items: RecordRow[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  sort: string;
  order: "asc" | "desc";
  columns: string[];
  fields: FieldDescriptor[];
  facets: Record<string, FacetValue[]>;
  condition_text: string;
  rule_count: number;
  query_text: string;
  searchable: string[];
}

export interface RecordQuery {
  filters?: Record<string, unknown>;
  query_text?: string;
  condition_tree?: QueryNode | null;
  columns?: string[];
  facets?: boolean;
  page?: number;
  page_size?: number;
  sort?: string;
  order?: "asc" | "desc";
}

export interface EntityRow {
  type: string;
  value: string;
  raw: string;
  position: number;
}

export interface CallRow {
  service: string;
  mocked: boolean;
  endpoint: string;
  duration_ms: number | null;
  ok: boolean;
  error: string;
  model: string;
  provider: string;
  input_tokens: number | null;
  output_tokens: number | null;
  service_seconds: number | null;
}

export interface RecordDetail {
  id: string;
  name: string;
  path: string;
  status: string;
  submitted_at: string | null;
  analysed_at: string | null;
  processing_seconds: number | null;
  sentiment: string;
  summary: string;
  entities_text: string;
  description: string;
  transcript: string;
  transcript_format: string;
  ocr_text: string;
  ocr_frames_count: number;
  persons: string[];
  model: string;
  prompt_hash: string;
  mocked: boolean;
  errors: Record<string, string>;
  failed_services: string[];
  entities: EntityRow[];
  calls: CallRow[];
  document: Record<string, unknown>;
}

export interface Related {
  items: { id: string; name: string; shared: string[]; count: number }[];
  shared_on: string[];
}

export interface Series {
  name: string;
  data: number[];
}

export interface ChartData {
  labels: string[];
  series: Series[];
}

export interface Kpi {
  key: string;
  label: string;
  value: number;
  unit: string;
  previous: number;
  delta: number;
  delta_pct: number | null;
  better: "up" | "down";
}

export interface DashboardRange {
  preset: string;
  from: string;
  to: string;
  previous_from?: string;
  previous_to?: string;
}

export interface Dashboard {
  range: DashboardRange;
  kpis: Kpi[];
  charts: {
    volume: ChartData;
    sentiment: ChartData;
    entity_types: ChartData;
    top_entities: ChartData;
    top_persons: ChartData;
    service_latency: ChartData;
  };
}

export interface ServiceStat {
  service: string;
  calls: number;
  mocked: number;
  live: number;
  failed: number;
  failure_rate: number;
  avg_ms: number | null;
  median_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  input_tokens: number;
  output_tokens: number;
}

export interface Statistics {
  range: DashboardRange;
  items: ServiceStat[];
  totals: {
    calls: number;
    live: number;
    mocked: number;
    failed: number;
    failure_rate: number;
    input_tokens: number;
    output_tokens: number;
  };
  models: { model: string; provider: string; calls: number; avg_ms: number | null; output_tokens: number }[];
  failures: { record_id: string; name: string; service: string; error: string; analysed_at: string }[];
  throughput: ChartData;
}

export interface SavedSearch {
  id: string;
  name: string;
  description: string;
  owner: string;
  payload: RecordQuery;
  pinned: boolean;
  run_count: number;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SavedSearchPage {
  items: SavedSearch[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ClientHealth {
  status: "ok" | "disabled" | "unreachable" | "degraded";
  url: string;
  tables?: string[];
  records?: number;
  calls?: number;
  saved_searches?: number;
  latest?: string | null;
  error?: string;
}

/**
 * One node of the advanced builder's condition tree.
 *
 * The shape react-awesome-query-builder exports and `client/rules.py` compiles
 * — kept structural rather than exact, because the library's own type is an
 * Immutable structure and what travels is the JSON.
 */
export interface QueryNode {
  id?: string;
  type: string;
  conjunction?: string;
  not?: boolean;
  properties?: Record<string, unknown>;
  children1?: Record<string, QueryNode> | QueryNode[];
}
