/**
 * The everyday narrowing: one text box, three menus, and a count.
 *
 * The text box sweeps every searchable column (summary, entities, transcript,
 * description, on-screen text, file name) — one `q`, one ILIKE per column,
 * server-side. It is debounced rather than submitted, because a filter that
 * needs Enter is a filter people forget to press Enter on; and the request it
 * fires is cancelled by the next keystroke, so a slow answer to an abandoned
 * question never lands.
 *
 * The menus are built from the *facets the data actually has*, counts and all,
 * not from a hardcoded list that drifts from it.
 */

import { CloseCircleOutlined, FilterOutlined, SearchOutlined } from "@ant-design/icons";
import { Badge, Button, Input, Select, Space, Tooltip, Typography } from "antd";
import { useEffect, useState } from "react";

import type { FacetValue, Meta } from "@/api/types";
import { SentimentTag } from "@/components/SentimentTag";

export interface SimpleFilters {
  q: string;
  sentiment: string[];
  status: string[];
  model: string[];
}

export const EMPTY_FILTERS: SimpleFilters = { q: "", sentiment: [], status: [], model: [] };

export function SearchBar({
  filters,
  facets,
  meta,
  total,
  loading,
  ruleCount,
  onChange,
  onAdvanced,
  onClear,
}: {
  filters: SimpleFilters;
  facets: Record<string, FacetValue[]>;
  meta?: Meta;
  total: number;
  loading: boolean;
  ruleCount: number;
  onChange: (next: SimpleFilters) => void;
  onAdvanced: () => void;
  onClear: () => void;
}) {
  // Local copy so typing is never held up by a request in flight; the parent
  // is told 300ms after the last keystroke.
  const [text, setText] = useState(filters.q);

  useEffect(() => setText(filters.q), [filters.q]);

  useEffect(() => {
    if (text === filters.q) return;
    const timer = window.setTimeout(() => onChange({ ...filters, q: text }), 300);
    return () => window.clearTimeout(timer);
  }, [text, filters, onChange]);

  const options = (name: string, fallback: string[] = []) => {
    const values = facets[name];
    if (values?.length) {
      return values.map((facet) => ({
        value: String(facet.value ?? ""),
        label: `${String(facet.value ?? "—") || "—"} (${facet.count})`,
      }));
    }
    return fallback.map((value) => ({ value, label: value }));
  };

  const dirty =
    Boolean(filters.q) ||
    filters.sentiment.length > 0 ||
    filters.status.length > 0 ||
    filters.model.length > 0 ||
    ruleCount > 0;

  return (
    <div className="search-bar">
      <Space.Compact className="search-bar-main">
        <Input
          allowClear
          size="middle"
          prefix={<SearchOutlined />}
          placeholder="Search summaries, entities, transcripts, on-screen text…"
          value={text}
          onChange={(event) => setText(event.target.value)}
          aria-label="Search every text field"
        />
      </Space.Compact>

      <Space wrap>
        <Select
          mode="multiple"
          allowClear
          className="search-facet"
          placeholder="Sentiment"
          value={filters.sentiment}
          onChange={(value) => onChange({ ...filters, sentiment: value })}
          options={options("sentiment", meta?.sentiments ?? [])}
          optionRender={(option) => <SentimentTag value={String(option.value)} />}
          maxTagCount="responsive"
          aria-label="Filter by sentiment"
        />
        <Select
          mode="multiple"
          allowClear
          className="search-facet"
          placeholder="Status"
          value={filters.status}
          onChange={(value) => onChange({ ...filters, status: value })}
          options={options("status", meta?.statuses ?? [])}
          maxTagCount="responsive"
          aria-label="Filter by status"
        />
        <Select
          mode="multiple"
          allowClear
          className="search-facet"
          placeholder="Model"
          value={filters.model}
          onChange={(value) => onChange({ ...filters, model: value })}
          options={options("model")}
          maxTagCount="responsive"
          aria-label="Filter by model"
        />

        <Tooltip title="Nested AND/OR conditions over every field">
          <Badge count={ruleCount} size="small" offset={[-4, 2]}>
            <Button icon={<FilterOutlined />} onClick={onAdvanced}>
              Advanced
            </Button>
          </Badge>
        </Tooltip>

        {dirty && (
          <Button type="text" icon={<CloseCircleOutlined />} onClick={onClear}>
            Clear
          </Button>
        )}
      </Space>

      <Typography.Text type="secondary" className="search-count" aria-live="polite">
        {loading ? "Searching…" : `${total.toLocaleString()} record${total === 1 ? "" : "s"}`}
      </Typography.Text>
    </div>
  );
}
