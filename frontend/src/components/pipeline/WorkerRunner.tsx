/**
 * Run one worker, here and now, and read what it produced.
 *
 * This is the other half of the pipeline's API: `POST /workers/{name}/run`
 * executes a single worker body inside the HTTP request and answers with its
 * return value. Nothing is published to Kafka and nothing downstream fires — so
 * it is the way to ask "what does :8823 actually say about this file?" without
 * committing a record to the corpus.
 *
 * Two knobs, both of which change what the answer means:
 *
 *   * **Chain** (default) runs the upstream workers first, so the worker gets
 *     the message its topic would have carried. Off, it runs alone on the
 *     message you supply — which is how to re-run W6 over branches you already
 *     have without paying for the extraction again.
 *   * **Persist** only matters to W7: with it off, the aggregator prints and
 *     returns the record but writes neither the file nor the database row, so
 *     a trial run cannot overwrite a real one.
 */

import { CaretRightOutlined } from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Checkbox, Form, Input, Select, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";

import { pipelineApi, type RunWorkerRequest, type WorkerSpec } from "@/api/pipeline";
import { errorText } from "@/lib/errors";

export function WorkerRunner() {
  const [worker, setWorker] = useState<string>("");
  const [path, setPath] = useState<string>("");
  const [chain, setChain] = useState(true);
  const [persist, setPersist] = useState(false);

  const catalog = useQuery({
    queryKey: ["workers"],
    queryFn: ({ signal }) => pipelineApi.workers(signal),
    staleTime: 5 * 60_000,
  });

  const run = useMutation({
    mutationFn: () => {
      const body: RunWorkerRequest = { path: path.trim(), chain };
      // Only sent for the aggregator, where it is the difference between a
      // trial and a real record.
      if (worker === "aggregator") body.persist = persist;
      return pipelineApi.runWorker(worker, body);
    },
  });

  const workers = catalog.data?.workers ?? [];
  const selected = workers.find((entry) => entry.worker === worker);

  return (
    <Card size="small" title="Run one worker" className="worker-runner">
      <Typography.Paragraph type="secondary">
        Runs inside this request and answers with what the worker produced. Nothing is
        published to Kafka, and no downstream worker is triggered.
      </Typography.Paragraph>

      <Form layout="vertical">
        <Space wrap align="end" size="middle">
          <Form.Item label="Worker" style={{ marginBottom: 0, minWidth: 240 }}>
            <Select
              value={worker || undefined}
              placeholder="Pick a worker"
              loading={catalog.isPending}
              onChange={setWorker}
              options={workers.map((entry) => ({
                value: entry.worker,
                label: `W${entry.step ?? "?"} · ${entry.worker}`,
              }))}
            />
          </Form.Item>
          <Form.Item label="Video path" style={{ marginBottom: 0, minWidth: 280 }}>
            <Input
              value={path}
              onChange={(event) => setPath(event.target.value)}
              placeholder="/video/migrants.mp4"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Checkbox checked={chain} onChange={(event) => setChain(event.target.checked)}>
              Run upstream workers first
            </Checkbox>
          </Form.Item>
          {worker === "aggregator" && (
            <Form.Item style={{ marginBottom: 0 }}>
              <Checkbox checked={persist} onChange={(event) => setPersist(event.target.checked)}>
                Write the record (file + database)
              </Checkbox>
            </Form.Item>
          )}
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              icon={<CaretRightOutlined />}
              disabled={!worker || !path.trim()}
              loading={run.isPending}
              onClick={() => run.mutate()}
            >
              Run
            </Button>
          </Form.Item>
        </Space>
      </Form>

      {selected && (
        <Space wrap size={[4, 4]} className="worker-meta">
          {selected.runs_first.length > 0 && (
            <Typography.Text type="secondary">
              Chained: {selected.runs_first.join(" → ")} → {selected.worker}
            </Typography.Text>
          )}
          {Object.entries(selected.mocked).map(([call, mocked]) => (
            <Tag key={call} color={mocked ? undefined : "success"}>
              {call}: {mocked ? "mocked" : "live"}
            </Tag>
          ))}
        </Space>
      )}

      {run.error && (
        <Alert
          type="error"
          showIcon
          className="worker-result"
          message="The worker failed"
          description={errorText(run.error, { action: "run this worker" })}
        />
      )}

      {run.data && (
        <div className="worker-result">
          <Typography.Text type="secondary">What the worker returned:</Typography.Text>
          <pre className="record-json">{JSON.stringify(run.data, null, 2)}</pre>
        </div>
      )}

      <Table<WorkerSpec>
        rowKey="worker"
        size="small"
        className="worker-table"
        pagination={false}
        loading={catalog.isPending}
        dataSource={workers}
        onRow={(row) => ({ onClick: () => setWorker(row.worker) })}
        columns={[
          { title: "#", dataIndex: "step", key: "step", width: 48 },
          { title: "Worker", dataIndex: "worker", key: "worker" },
          { title: "Kind", dataIndex: "kind", key: "kind", width: 110 },
          {
            title: "Reads",
            dataIndex: "topics_in",
            key: "topics_in",
            render: (topics: string[]) => topics.join(", ") || "—",
          },
          {
            title: "Writes",
            dataIndex: "topics_out",
            key: "topics_out",
            render: (topics: string[]) => topics.join(", ") || "—",
          },
          {
            title: "AI calls",
            dataIndex: "mocked",
            key: "mocked",
            render: (mocked: Record<string, boolean>) =>
              Object.keys(mocked).length === 0 ? (
                <Typography.Text type="secondary">none</Typography.Text>
              ) : (
                <Space size={[4, 4]} wrap>
                  {Object.entries(mocked).map(([call, isMocked]) => (
                    <Tag key={call} color={isMocked ? undefined : "success"}>
                      {call}
                    </Tag>
                  ))}
                </Space>
              ),
          },
        ]}
      />
    </Card>
  );
}
