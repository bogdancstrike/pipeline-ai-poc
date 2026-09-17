/**
 * The results, as a table.
 *
 * Sorting and paging are server-side without exception: a table that sorts the
 * 25 rows it downloaded presents "the newest" as if it had looked at all
 * 20,000. AntD's own sorter is therefore wired to the query rather than to its
 * internal comparison.
 *
 * Columns are chosen by the caller and described by the API, so a column added
 * to `resources.py` becomes selectable here with no change to this file.
 */

import { Table, Tooltip, Typography } from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import type { SorterResult } from "antd/es/table/interface";
import { useNavigate } from "react-router-dom";

import type { FieldDescriptor, RecordPage, RecordRow } from "@/api/types";
import { SentimentTag } from "@/components/SentimentTag";
import { StatusTag } from "@/components/StatusTag";
import { formatNumber } from "@/lib/formats";
import { ago, dateTime, duration } from "@/lib/time";

export function ResultsTable({
  page,
  loading,
  onQueryChange,
  onOpen,
}: {
  page?: RecordPage;
  loading: boolean;
  onQueryChange: (next: { page?: number; page_size?: number; sort?: string; order?: "asc" | "desc" }) => void;
  onOpen: (row: RecordRow) => void;
}) {
  const navigate = useNavigate();
  const fields = new Map((page?.fields ?? []).map((field) => [field.name, field]));

  const columns: ColumnsType<RecordRow> = (page?.columns ?? []).map((name) => {
    const field = fields.get(name);
    return {
      key: name,
      dataIndex: name,
      title: field?.label ?? name,
      sorter: field?.sortable ?? false,
      sortOrder:
        page?.sort === name ? (page.order === "asc" ? "ascend" : "descend") : null,
      ellipsis: field?.kind === "text",
      align: field?.kind === "number" ? "right" : undefined,
      width: widthFor(name, field),
      render: (value: unknown, row: RecordRow) => renderCell(name, value, row, field),
    };
  });

  // Always openable, whatever columns the reader picked.
  columns.unshift({
    key: "name",
    dataIndex: "name",
    title: "Video",
    fixed: "left",
    width: 260,
    render: (value: string, row: RecordRow) => (
      <div className="cell-video">
        <a
          onClick={(event) => {
            event.preventDefault();
            onOpen(row);
          }}
          href={`/records/${encodeURIComponent(row.id)}`}
        >
          {value || row.id}
        </a>
        {row.summary_preview ? (
          <Typography.Text type="secondary" ellipsis className="cell-preview">
            {row.summary_preview}
          </Typography.Text>
        ) : null}
      </div>
    ),
  });

  const pagination: TablePaginationConfig = {
    current: page?.page ?? 1,
    pageSize: page?.page_size ?? 25,
    total: page?.total ?? 0,
    showSizeChanger: true,
    pageSizeOptions: [10, 25, 50, 100, 200],
    showTotal: (total, range) =>
      `${range[0].toLocaleString()}–${range[1].toLocaleString()} of ${total.toLocaleString()}`,
  };

  return (
    <Table<RecordRow>
      rowKey="id"
      size="small"
      loading={loading}
      dataSource={page?.items ?? []}
      columns={columns}
      pagination={pagination}
      scroll={{ x: "max-content" }}
      onRow={(row) => ({
        onDoubleClick: () => navigate(`/records/${encodeURIComponent(row.id)}`),
      })}
      onChange={(next, _filters, sorter) => {
        const single = Array.isArray(sorter) ? sorter[0] : (sorter as SorterResult<RecordRow>);
        onQueryChange({
          page: next.current ?? 1,
          page_size: next.pageSize ?? 25,
          ...(single?.field
            ? {
                sort: String(single.field),
                order: single.order === "ascend" ? "asc" : "desc",
              }
            : {}),
        });
      }}
    />
  );
}

function widthFor(name: string, field?: FieldDescriptor): number | undefined {
  if (name.endsWith("_at")) return 170;
  if (field?.kind === "number") return 120;
  if (field?.kind === "enum" || field?.kind === "bool") return 130;
  return undefined;
}

function renderCell(
  name: string,
  value: unknown,
  row: RecordRow,
  field?: FieldDescriptor,
): React.ReactNode {
  if (name === "sentiment") return <SentimentTag value={String(value ?? "")} />;
  if (name === "status") return <StatusTag status={String(value ?? "")} errors={row["error_count"] as number} />;
  if (name === "processing_seconds") return duration(value as number | null);
  if (name.endsWith("_at")) {
    const text = value ? String(value) : null;
    return text ? <Tooltip title={dateTime(text)}>{ago(text)}</Tooltip> : "—";
  }
  if (field?.kind === "bool") return value ? "yes" : "no";
  if (field?.kind === "number") {
    return value === null || value === undefined
      ? "—"
      : formatNumber(Number(value), { maximumFractionDigits: 2 });
  }
  if (field?.kind === "json" && Array.isArray(value)) return value.join(", ") || "—";
  const text = value === null || value === undefined ? "" : String(value);
  return text || "—";
}
