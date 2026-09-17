/**
 * The window every number on a page is computed over.
 *
 * Server-resolved presets rather than two dates the browser subtracts: "this
 * month" has to mean the same thing to the KPI header and to the chart under
 * it, and the only way to guarantee that is for one process to decide it.
 */

import { Segmented, Space } from "antd";

export const RANGES = [
  { label: "7 days", value: "last_7_days" },
  { label: "30 days", value: "last_30_days" },
  { label: "90 days", value: "last_90_days" },
  { label: "This month", value: "current_month" },
  { label: "This year", value: "current_year" },
] as const;

export function RangePicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <Space>
      <Segmented
        size="small"
        aria-label="Time range"
        value={value}
        onChange={(next) => onChange(String(next))}
        options={RANGES.map((range) => ({ label: range.label, value: range.value }))}
      />
    </Space>
  );
}
