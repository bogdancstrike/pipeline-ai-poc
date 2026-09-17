import { Tag, Tooltip } from "antd";

import { SENTIMENT_COLORS } from "@/components/charts/options";

/**
 * The sentiment word, coloured the same everywhere it is shown.
 *
 * An unknown value is rendered as itself rather than dropped: the prompt asks
 * for one of three words and a model that answered something else is a thing
 * to see, not to hide.
 */
export function SentimentTag({ value }: { value: string }) {
  const word = (value || "").toUpperCase();
  if (!word) return <Tag>—</Tag>;

  const known = word in SENTIMENT_COLORS && word !== "";
  const tag = <Tag color={SENTIMENT_COLORS[word] ?? undefined}>{word}</Tag>;
  return known ? tag : <Tooltip title="Not one of POSITIVE / NEUTRAL / NEGATIVE">{tag}</Tooltip>;
}
