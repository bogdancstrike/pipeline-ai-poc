/**
 * Everything one video produced, in the order somebody reads it.
 *
 * Summary first, because it is the answer; then what was heard, what was seen
 * and who was in it; then the machinery — which service answered, how fast,
 * with which model — and last the record as JSON, which is the file on disk.
 *
 * A service that failed is shown where its text would have been, rather than
 * as a missing section: "the transcript is empty" and "transcription refused"
 * look identical otherwise, and only one of them is worth re-running.
 */

import { Alert, Card, Descriptions, Empty, Space, Table, Tabs, Tag, Typography } from "antd";

import type { CallRow, RecordDetail } from "@/api/types";
import { EnrichmentPanels } from "@/components/explorer/EnrichmentPanels";
import { VideoPlayer } from "@/components/explorer/VideoPlayer";
import { SentimentTag } from "@/components/SentimentTag";
import { StatusTag } from "@/components/StatusTag";
import { errorText } from "@/lib/errors";
import { dateTime, duration, millis } from "@/lib/time";

export function RecordView({ record, error }: { record?: RecordDetail; error?: unknown }) {
  if (error) {
    return <Alert type="error" showIcon message="This record could not be read" description={errorText(error)} />;
  }
  if (!record) return <Empty description="No record" />;

  return (
    <div className="record-view">
      <Descriptions size="small" column={2} bordered className="record-facts">
        <Descriptions.Item label="Status">
          <Space>
            <StatusTag status={record.status} errors={record.failed_services.length} />
            <SentimentTag value={record.sentiment} />
            {record.mocked && <Tag>mocked run</Tag>}
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="Analysed">{dateTime(record.analysed_at)}</Descriptions.Item>
        <Descriptions.Item label="Path">
          <Typography.Text code copyable>
            {record.path}
          </Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="Processing">{duration(record.processing_seconds)}</Descriptions.Item>
        <Descriptions.Item label="Model">{record.model || "—"}</Descriptions.Item>
        <Descriptions.Item label="Record id">
          <Typography.Text code copyable>
            {record.id}
          </Typography.Text>
        </Descriptions.Item>
      </Descriptions>

      {record.failed_services.length > 0 && (
        <Alert
          type="warning"
          showIcon
          className="record-alert"
          message={`${record.failed_services.length} service(s) did not answer`}
          description={
            <ul className="record-errors">
              {Object.entries(record.errors).map(([service, message]) => (
                <li key={service}>
                  <strong>{service}</strong>: {message}
                </li>
              ))}
            </ul>
          }
        />
      )}

      <Tabs
        defaultActiveKey="enrichment"
        items={[
          {
            key: "enrichment",
            label: "Enrichment",
            children: (
              <div className="record-enrichment">
                <VideoPlayer record={record} />
                <EnrichmentPanels record={record} />
              </div>
            ),
          },
          {
            key: "calls",
            label: `Calls (${record.calls.length})`,
            children: <CallsTable calls={record.calls} />,
          },
          {
            key: "json",
            label: "JSON",
            children: (
              <Card size="small" title="The record, as written to output/">
                <pre className="record-json">{JSON.stringify(record.document, null, 2)}</pre>
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}

function CallsTable({ calls }: { calls: CallRow[] }) {
  return (
    <Table<CallRow>
      rowKey="service"
      size="small"
      pagination={false}
      dataSource={calls}
      columns={[
        { title: "Service", dataIndex: "service", key: "service" },
        {
          title: "Outcome",
          key: "ok",
          render: (_, row) =>
            row.ok ? (
              row.mocked ? (
                <Tag>mocked</Tag>
              ) : (
                <Tag color="success">answered</Tag>
              )
            ) : (
              <Tag color="error">failed</Tag>
            ),
        },
        {
          title: "Time",
          dataIndex: "duration_ms",
          key: "duration_ms",
          align: "right",
          render: (value: number | null) => millis(value),
        },
        { title: "Model", dataIndex: "model", key: "model", render: (v: string) => v || "—" },
        {
          title: "Tokens in/out",
          key: "tokens",
          align: "right",
          render: (_, row) =>
            row.input_tokens || row.output_tokens
              ? `${row.input_tokens ?? 0} / ${row.output_tokens ?? 0}`
              : "—",
        },
        {
          title: "Endpoint",
          dataIndex: "endpoint",
          key: "endpoint",
          ellipsis: true,
          render: (value: string, row) => value || (row.mocked ? "—" : ""),
        },
      ]}
    />
  );
}
