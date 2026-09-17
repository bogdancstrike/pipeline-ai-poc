/**
 * The seven things the pipeline produced, each in its own panel.
 *
 * Stacked, one under the other, in pipeline order — because that is the order
 * they were produced in and the order somebody reads them: who is in it, what
 * it looks like, what is said, what is written on screen, then the three
 * prompted answers over all of it. A grid would put the transcript beside the
 * OCR and invite reading them as a pair, which they are not.
 *
 *   face match   W2  :8821 /match
 *   description  W3  :8822 /describe
 *   transcript   W4  :8824 /transcribe
 *   on-screen    W5  :8823 /ocr
 *   summary      W6  :8825 summary.txt
 *   entities     W6  :8825 entities.txt
 *   sentiment    W6  :8825 sentiment.txt
 *
 * A service that failed shows its error *where its text would have been*
 * rather than as a missing panel: "the transcript is empty" and "transcription
 * refused" look identical otherwise, and only one of them is worth re-running.
 */

import { Alert, Card, Empty, Space, Tag, Typography } from "antd";
import type { ReactNode } from "react";

import type { RecordDetail } from "@/api/types";
import { SentimentTag } from "@/components/SentimentTag";

export function EnrichmentPanels({ record }: { record: RecordDetail }) {
  const failure = (service: string) => record.errors[service];

  return (
    <div className="enrichment">
      <Panel
        title="Face match"
        service="face-match-main · :8821"
        error={failure("face-match-main")}
        empty="Nobody was matched in this video."
        filled={record.persons.length > 0}
      >
        <Space wrap>
          {record.persons.map((person) => (
            <Tag key={person} color="processing">
              {person}
            </Tag>
          ))}
        </Space>
      </Panel>

      <Panel
        title="Description"
        service="video-describe-354b · :8822"
        error={failure("video-describe-354b")}
        filled={Boolean(record.description)}
      >
        <Typography.Paragraph className="record-prose">{record.description}</Typography.Paragraph>
      </Panel>

      <Panel
        title={`Transcript${record.transcript_format ? ` · ${record.transcript_format}` : ""}`}
        service="transcribe · :8824"
        error={failure("transcribe")}
        empty="No speech was transcribed."
        filled={Boolean(record.transcript)}
      >
        <pre className="record-pre">{record.transcript}</pre>
      </Panel>

      <Panel
        title={`On-screen text · ${record.ocr_frames_count} frames`}
        service="video-ocr · :8823"
        error={failure("video-ocr")}
        empty="No text was read off the frames."
        filled={Boolean(record.ocr_text)}
      >
        <pre className="record-pre">{record.ocr_text}</pre>
      </Panel>

      <Panel
        title="Summary"
        service="summarize · :8825 · summary.txt"
        error={failure("summary")}
        filled={Boolean(record.summary)}
      >
        <Typography.Paragraph className="record-prose">{record.summary}</Typography.Paragraph>
      </Panel>

      <Panel
        title={`Entities · ${record.entities.length}`}
        service="summarize · :8825 · entities.txt"
        error={failure("entities")}
        empty="No entities were extracted."
        filled={record.entities.length > 0}
      >
        <Space wrap size={[4, 8]}>
          {record.entities.map((entity) => (
            <Tag key={`${entity.type}-${entity.value}-${entity.position}`}>
              <strong>{entity.type}</strong> {entity.value}
            </Tag>
          ))}
        </Space>
      </Panel>

      <Panel
        title="Sentiment"
        service="summarize · :8825 · sentiment.txt"
        error={failure("sentiment")}
        filled={Boolean(record.sentiment)}
      >
        <SentimentTag value={record.sentiment} />
      </Panel>
    </div>
  );
}

function Panel({
  title,
  service,
  error,
  empty = "Nothing was produced.",
  filled,
  children,
}: {
  title: string;
  service: string;
  error?: string;
  empty?: string;
  filled: boolean;
  children: ReactNode;
}) {
  return (
    <Card
        size="small"
        title={title}
        extra={<span className="card-note">{service}</span>}
        className="enrichment-card"
      >
      {error ? (
        <Alert type="error" showIcon message="This service did not answer" description={error} />
      ) : filled ? (
        children
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty} />
      )}
    </Card>
  );
}
