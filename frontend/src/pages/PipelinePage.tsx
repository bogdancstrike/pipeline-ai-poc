/**
 * The wiring behind the records.
 *
 * Three things, in the order somebody reaches for them: the prompts that
 * decide what the next video's summary says, the runner for trying one worker
 * against one file, and — last, because it is reference rather than a control —
 * where the five AI services live and whether each is answering or mocked.
 *
 * It is deliberately flat. This page used to be five stacked cards, two of them
 * raw JSON and a database status nobody came here for, and the two things it is
 * actually for were buried in the middle of it. Sections with a rule under the
 * heading say the same thing as a card and take a tenth of the ink.
 *
 * Everything still comes from the pipeline's own endpoints, so "why does every
 * record say mocked?" is answerable without a shell on the container.
 */

import { PlusOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { App, Alert, Button, Skeleton, Tag, Tooltip, Typography } from "antd";
import { useState, type ReactNode } from "react";

import { api } from "@/api/client";
import { PageHeader } from "@/app/AppShell";
import { AnalyzeModal } from "@/components/pipeline/AnalyzeModal";
import { PromptEditor } from "@/components/pipeline/PromptEditor";
import { WorkerRunner } from "@/components/pipeline/WorkerRunner";
import { errorText } from "@/lib/errors";

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
  const { message } = App.useApp();
  const [analyzeOpen, setAnalyzeOpen] = useState(false);

  const config = useQuery({
    queryKey: ["pipeline-config"],
    queryFn: ({ signal }) => api.get<PipelineConfig>("/pipeline/config", { signal }),
  });

  return (
    <div className="page pipeline">
      <PageHeader
        title="Pipeline"
        blurb="Edit the prompts the next video will use, run a single worker, and see where each AI service lives."
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAnalyzeOpen(true)}>
            Analyse a video
          </Button>
        }
      />

      {config.error && (
        <Alert
          type="error"
          showIcon
          message="The pipeline did not answer"
          description={errorText(config.error, { action: "read the pipeline configuration" })}
        />
      )}

      <Section
        title="Summary prompts"
        note="Posted to :8825 in full. A saved prompt applies to the next video — no restart."
      >
        <PromptEditor />
      </Section>

      <Section
        title="Run one worker"
        note="Runs inside this request. Nothing is published to Kafka, and no downstream worker fires."
      >
        <WorkerRunner />
      </Section>

      <Section title="AI services">
        <Services config={config.data} loading={config.isPending} />
      </Section>

      <AnalyzeModal
        open={analyzeOpen}
        onClose={() => setAnalyzeOpen(false)}
        onSubmitted={(id) =>
          message.success(`Submitted as ${id} — watch it land on the Records page.`)
        }
      />
    </div>
  );
}

/**
 * One part of the page: a heading, an optional line saying what it is for, and
 * a rule to separate it from the next one.
 *
 * A `<section>` with a heading rather than a `<Card>`: three cards stacked down
 * a page is three borders, three shadows and three paddings drawn around
 * content that is already obviously separate.
 */
function Section({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section className="pipeline-section">
      <div className="pipeline-section-head">
        <Typography.Title level={5} className="pipeline-section-title">
          {title}
        </Typography.Title>
        {note && (
          <Typography.Text type="secondary" className="pipeline-section-note">
            {note}
          </Typography.Text>
        )}
      </div>
      {children}
    </section>
  );
}

/**
 * Where the five services live, and whether each is answering or canned.
 *
 * A strip of one line each rather than a table: the columns were a name, a URL
 * and a word, and a table around three values is furniture. The full URL is on
 * the hostname's tooltip, because the port is what tells them apart.
 */
function Services({ config, loading }: { config?: PipelineConfig; loading: boolean }) {
  if (loading) return <Skeleton active paragraph={{ rows: 3 }} />;

  const services = Object.entries(config?.ai_services ?? {});
  if (!services.length) {
    return <Typography.Text type="secondary">The pipeline named no services.</Typography.Text>;
  }

  return (
    <div className="service-strip">
      {services.map(([name, url]) => {
        const mocked = config?.mocked?.[name] ?? config?.mocked?.[name.split(":")[0] ?? name];
        return (
          <div key={name} className="service-row">
            <span className="service-name">{name}</span>
            <Tooltip title={url}>
              <span className="service-url">{shortUrl(url)}</span>
            </Tooltip>
            <span className="service-mode">
              {mocked ? <Tag>mocked</Tag> : <Tag color="success">live</Tag>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** `http://172.17.12.80:8821` -> `172.17.12.80:8821` — the host is the same for all five. */
function shortUrl(url: string): string {
  return String(url).replace(/^https?:\/\//, "").replace(/\/$/, "");
}
