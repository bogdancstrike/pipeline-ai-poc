/**
 * Run one worker, here and now, and read what it produced.
 *
 * `POST /workers/{name}/run` executes a single worker body inside the HTTP
 * request and answers with its return value. Nothing is published to Kafka and
 * nothing downstream fires — so it is the way to ask "what does :8823 actually
 * say about this file?" without committing a record to the corpus.
 *
 * Two knobs, both of which change what the answer means:
 *
 *   * **Chain** (default) runs the upstream workers first, so the worker gets
 *     the message its topic would have carried. Off, it runs alone on the
 *     message supplied — which is how to re-run W6 over branches you already
 *     have without paying for the extraction again.
 *   * **Persist** only matters to W7: with it off, the aggregator prints and
 *     returns the record but writes neither the file nor the database row, so
 *     a trial run cannot overwrite a real one.
 *
 * The seven-row catalogue that used to sit under this is gone. Its Reads and
 * Writes columns were the Kafka topology — the thing this page was asked to
 * stop being about — and everything else it said is on the picker, or on the
 * line that appears once a worker is chosen.
 */

import { CaretRightOutlined } from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Checkbox, Input, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { pipelineApi, type RunWorkerRequest } from "@/api/pipeline";
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
    <div className="worker-runner">
      <div className="worker-controls">
        <Select
          className="worker-picker"
          value={worker || undefined}
          placeholder="Pick a worker"
          loading={catalog.isPending}
          onChange={setWorker}
          options={workers.map((entry) => ({
            value: entry.worker,
            label: `W${entry.step ?? "?"} · ${entry.worker}`,
          }))}
          aria-label="Worker to run"
        />
        <Input
          className="worker-path"
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="/video/migrants.mp4"
          aria-label="Video path"
          onPressEnter={() => {
            if (worker && path.trim()) run.mutate();
          }}
        />
        <Button
          type="primary"
          icon={<CaretRightOutlined />}
          disabled={!worker || !path.trim()}
          loading={run.isPending}
          onClick={() => run.mutate()}
        >
          Run
        </Button>
      </div>

      <Space size="middle" wrap className="worker-options">
        <Checkbox checked={chain} onChange={(event) => setChain(event.target.checked)}>
          Run upstream workers first
        </Checkbox>
        {worker === "aggregator" && (
          <Checkbox checked={persist} onChange={(event) => setPersist(event.target.checked)}>
            Write the record (file + database)
          </Checkbox>
        )}
      </Space>

      {/* What the chosen worker is, in one line: what runs before it, and
          which of its AI calls are canned. */}
      {selected && (
        <Space wrap size={[6, 4]} className="worker-meta">
          {selected.runs_first.length > 0 && (
            <Typography.Text type="secondary">
              {selected.runs_first.join(" → ")} → {selected.worker}
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
          <Typography.Text type="secondary" className="worker-result-label">
            What the worker returned
          </Typography.Text>
          <pre className="record-json">{JSON.stringify(run.data, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
