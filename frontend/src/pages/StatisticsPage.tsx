/**
 * What it cost to produce the corpus.
 *
 * The dashboard answers "what is in it"; this answers "how is the pipeline
 * behaving" — per-service call counts, latency, failures and token throughput,
 * built from the provenance W7 stored alongside each record.
 *
 * Latency is a median and a p95, not only a mean: one cold model load is
 * enough to make a mean describe a run that never happened. Mocked calls are
 * counted separately for the same reason — folding a canned answer into a
 * latency average reports the pipeline as instantaneous.
 */

import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Col, Row, Statistic, Table, Tag, Typography } from "antd";
import { useState } from "react";

import { dashboardApi } from "@/api/dashboard";
import type { ServiceStat } from "@/api/types";
import { PageHeader } from "@/app/AppShell";
import { ChartCard } from "@/components/ChartCard";
import { RangePicker } from "@/components/RangePicker";
import { countAndLatency } from "@/components/charts/options";
import { errorText } from "@/lib/errors";
import { formatNumber } from "@/lib/formats";
import { ago, millis } from "@/lib/time";

export default function StatisticsPage() {
  const [range, setRange] = useState("last_30_days");

  const { data, isPending, error } = useQuery({
    queryKey: ["statistics", range],
    queryFn: ({ signal }) => dashboardApi.statistics({ range }, signal),
  });

  return (
    <div className="page">
      <PageHeader
        title="Statistics"
        blurb="Per-service call counts, latency and failures, from the provenance stored with every record."
        extra={<RangePicker value={range} onChange={setRange} />}
      />

      {error && (
        <Alert
          type="error"
          showIcon
          message="The statistics could not be built"
          description={errorText(error, { action: "read the call log" })}
        />
      )}

      <Row gutter={[12, 12]} className="kpi-row">
        <Col xs={12} lg={6}>
          <Card size="small" loading={isPending}>
            <Statistic title="AI calls" value={data?.totals.calls ?? 0} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" loading={isPending}>
            <Statistic
              title="Live / mocked"
              value={`${data?.totals.live ?? 0} / ${data?.totals.mocked ?? 0}`}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" loading={isPending}>
            <Statistic
              title="Failure rate"
              value={data?.totals.failure_rate ?? 0}
              suffix="%"
              valueStyle={(data?.totals.failure_rate ?? 0) > 0 ? { color: "#dc2626" } : undefined}
            />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" loading={isPending}>
            <Statistic
              title="Tokens in / out"
              value={`${formatNumber(data?.totals.input_tokens ?? 0)} / ${formatNumber(
                data?.totals.output_tokens ?? 0,
              )}`}
            />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="Per service" loading={isPending} className="stats-table">
        <Table<ServiceStat>
          rowKey="service"
          size="small"
          pagination={false}
          dataSource={data?.items ?? []}
          columns={[
            { title: "Service", dataIndex: "service", key: "service" },
            { title: "Calls", dataIndex: "calls", key: "calls", align: "right" },
            {
              title: "Live",
              dataIndex: "live",
              key: "live",
              align: "right",
              render: (value: number, row) =>
                row.mocked ? (
                  <span>
                    {value} <Typography.Text type="secondary">({row.mocked} mocked)</Typography.Text>
                  </span>
                ) : (
                  value
                ),
            },
            {
              title: "Median",
              dataIndex: "median_ms",
              key: "median_ms",
              align: "right",
              render: (value: number | null) => millis(value),
            },
            {
              title: "p95",
              dataIndex: "p95_ms",
              key: "p95_ms",
              align: "right",
              render: (value: number | null) => millis(value),
            },
            {
              title: "Max",
              dataIndex: "max_ms",
              key: "max_ms",
              align: "right",
              render: (value: number | null) => millis(value),
            },
            {
              title: "Failed",
              dataIndex: "failed",
              key: "failed",
              align: "right",
              render: (value: number, row) =>
                value ? <Tag color="error">{value} ({row.failure_rate}%)</Tag> : <Tag>0</Tag>,
            },
            {
              title: "Tokens out",
              dataIndex: "output_tokens",
              key: "output_tokens",
              align: "right",
              render: (value: number) => (value ? formatNumber(value) : "—"),
            },
          ]}
        />
      </Card>

      <Row gutter={[12, 12]}>
        <Col xs={24} xl={14}>
          <ChartCard
            title="Calls and latency per day"
            loading={isPending}
            data={data?.throughput}
            option={countAndLatency(data?.throughput ?? { labels: [], series: [] })}
            height={300}
          />
        </Col>
        <Col xs={24} xl={10}>
          <Card size="small" title="Models" loading={isPending}>
            <Table
              rowKey={(row) => `${row.model}-${row.provider}`}
              size="small"
              pagination={false}
              locale={{ emptyText: "No model reported in this window." }}
              dataSource={data?.models ?? []}
              columns={[
                { title: "Model", dataIndex: "model", key: "model" },
                { title: "Provider", dataIndex: "provider", key: "provider" },
                { title: "Calls", dataIndex: "calls", key: "calls", align: "right" },
                {
                  title: "Avg",
                  dataIndex: "avg_ms",
                  key: "avg_ms",
                  align: "right",
                  render: (value: number | null) => millis(value),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="Recent failures" loading={isPending}>
        <Table
          rowKey={(row) => `${row.record_id}-${row.service}`}
          size="small"
          pagination={false}
          locale={{ emptyText: "Every call in this window answered." }}
          dataSource={data?.failures ?? []}
          columns={[
            { title: "Video", dataIndex: "name", key: "name" },
            { title: "Service", dataIndex: "service", key: "service", width: 180 },
            { title: "Error", dataIndex: "error", key: "error", ellipsis: true },
            {
              title: "When",
              dataIndex: "analysed_at",
              key: "analysed_at",
              width: 140,
              render: (value: string) => ago(value),
            },
          ]}
        />
      </Card>
    </div>
  );
}
