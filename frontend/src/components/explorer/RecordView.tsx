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

import { Alert, Card, Col, Descriptions, Empty, Row, Space, Table, Tabs, Tag, Typography } from "antd";

import type { CallRow, RecordDetail } from "@/api/types";
import { SentimentTag } from "@/components/SentimentTag";
import { StatusTag } from "@/components/StatusTag";
import { errorText } from "@/lib/errors";
import { dateTime, duration, millis } from "@/lib/time";

export function RecordView({ record, error }: { record?: RecordDetail; error?: unknown }) {
  if (error) {
    return <Alert type="error" showIcon message="This record could not be read" description={errorText(error)} />;
  }
  if (!record) return <Empty description="No record" />;

  const failed = (service: string) => record.errors[service];

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
        defaultActiveKey="summary"
        items={[
          {
            key: "summary",
            label: "Summary",
            children: (
              <Row gutter={[12, 12]}>
                <Col span={24}>
                  <Card size="small" title="Summary">
                    <Prose text={record.summary} missing={failed("summary")} />
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card size="small" title={`Entities (${record.entities.length})`}>
                    {record.entities.length ? (
                      <Space wrap size={[4, 8]}>
                        {record.entities.map((entity) => (
                          <Tag key={`${entity.type}-${entity.value}-${entity.position}`}>
                            <strong>{entity.type}</strong> {entity.value}
                          </Tag>
                        ))}
                      </Space>
                    ) : (
                      <Prose text="" missing={failed("entities")} />
                    )}
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card size="small" title={`Persons (${record.persons.length})`}>
                    {record.persons.length ? (
                      <Space wrap>
                        {record.persons.map((person) => (
                          <Tag key={person} color="processing">
                            {person}
                          </Tag>
                        ))}
                      </Space>
                    ) : (
                      <Prose text="" missing={failed("face-match-main")} empty="Nobody was matched." />
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "transcript",
            label: "Transcript",
            children: (
              <Card size="small" title={`Transcript${record.transcript_format ? ` · ${record.transcript_format}` : ""}`}>
                <Prose text={record.transcript} missing={failed("transcribe")} pre />
              </Card>
            ),
          },
          {
            key: "video",
            label: "Video & OCR",
            children: (
              <Row gutter={[12, 12]}>
                <Col span={24}>
                  <Card size="small" title="Description">
                    <Prose text={record.description} missing={failed("video-describe-354b")} />
                  </Card>
                </Col>
                <Col span={24}>
                  <Card size="small" title={`On-screen text · ${record.ocr_frames_count} frames`}>
                    <Prose text={record.ocr_text} missing={failed("video-ocr")} pre />
                  </Card>
                </Col>
              </Row>
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

function Prose({
  text,
  missing,
  pre,
  empty = "Nothing was produced.",
}: {
  text: string;
  missing?: string;
  pre?: boolean;
  empty?: string;
}) {
  if (missing) {
    return <Alert type="error" showIcon message="This service did not answer" description={missing} />;
  }
  if (!text) return <Typography.Text type="secondary">{empty}</Typography.Text>;
  return pre ? (
    <pre className="record-pre">{text}</pre>
  ) : (
    <Typography.Paragraph className="record-prose">{text}</Typography.Paragraph>
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
