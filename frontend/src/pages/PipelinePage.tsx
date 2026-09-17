/**
 * The wiring behind the records.
 *
 * Everything on this page comes from the pipeline's own endpoints — the ones
 * that existed before this client app did (`/pipeline/config`,
 * `/pipeline/health`) — so it answers "why does every record say mocked?" or
 * "which prompt produced this summary?" without a shell on the container.
 */

import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Col, Descriptions, Row, Table, Tag } from "antd";

import { api } from "@/api/client";
import { metaApi } from "@/api/meta";
import { PageHeader } from "@/app/AppShell";
import { errorText } from "@/lib/errors";
import { ago } from "@/lib/time";

interface PipelineConfig {
  ai_services: Record<string, string>;
  mocked: Record<string, boolean>;
  prompts: Record<string, unknown>;
  summarize_inputs: Record<string, unknown>;
  transcribe_defaults: Record<string, unknown>;
  output: Record<string, unknown>;
  topics: Record<string, string>;
}

export default function PipelinePage() {
  const config = useQuery({
    queryKey: ["pipeline-config"],
    queryFn: ({ signal }) => api.get<PipelineConfig>("/pipeline/config", { signal }),
  });

  const health = useQuery({
    queryKey: ["client-health"],
    queryFn: ({ signal }) => metaApi.health(signal),
  });

  const services = Object.entries(config.data?.ai_services ?? {}).map(([name, url]) => ({
    name,
    url,
    mocked: config.data?.mocked?.[name] ?? config.data?.mocked?.[name.split(":")[0] ?? name],
  }));

  return (
    <div className="page">
      <PageHeader
        title="Pipeline"
        blurb="Where each AI service lives, which calls are mocked, and what the client app is reading."
      />

      {config.error && (
        <Alert
          type="error"
          showIcon
          message="The pipeline did not answer"
          description={errorText(config.error, { action: "read the pipeline configuration" })}
        />
      )}

      <Row gutter={[12, 12]}>
        <Col xs={24} xl={14}>
          <Card size="small" title="AI services" loading={config.isPending}>
            <Table
              rowKey="name"
              size="small"
              pagination={false}
              dataSource={services}
              columns={[
                { title: "Service", dataIndex: "name", key: "name" },
                { title: "Endpoint", dataIndex: "url", key: "url", ellipsis: true },
                {
                  title: "Mode",
                  dataIndex: "mocked",
                  key: "mocked",
                  width: 110,
                  render: (mocked: boolean | undefined) =>
                    mocked ? <Tag>mocked</Tag> : <Tag color="success">live</Tag>,
                },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card size="small" title="Records database" loading={health.isPending}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="Status">
                {health.data?.status === "ok" ? (
                  <Tag color="success">connected</Tag>
                ) : (
                  <Tag color="error">{health.data?.status ?? "unreachable"}</Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="URL">{health.data?.url ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Records">{health.data?.records ?? 0}</Descriptions.Item>
              <Descriptions.Item label="AI calls stored">{health.data?.calls ?? 0}</Descriptions.Item>
              <Descriptions.Item label="Latest record">
                {health.data?.latest ? ago(health.data.latest) : "none yet"}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card size="small" title="Summary prompts" loading={config.isPending}>
            <pre className="record-json">{JSON.stringify(config.data?.prompts ?? {}, null, 2)}</pre>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title="Kafka topics" loading={config.isPending}>
            <pre className="record-json">{JSON.stringify(config.data?.topics ?? {}, null, 2)}</pre>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
