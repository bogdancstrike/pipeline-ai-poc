/**
 * Chart options, one function per shape.
 *
 * The rules that would otherwise be re-decided per chart are decided here:
 *
 * * **A category axis with long labels rotates rather than truncates.** An
 *   entity called "Red Cross" abbreviated to "Red…" is one a reader cannot
 *   match to the table beside it.
 * * **A time axis is labelled by day, not by ISO string.** The series carries
 *   the full timestamp for the tooltip.
 * * **A donut, never a pie, for a breakdown**, with the total in the middle:
 *   the number a reader wants first is the one a pie leaves them to add up.
 * * **Nothing is coloured by index alone where the value has a meaning.**
 *   Sentiment is green/grey/red wherever it appears, because a reader learns
 *   the mapping once.
 */

import { SEMANTIC, SERIES } from "@/theme/tokens";
import type { ChartData } from "@/api/types";
import { day } from "@/lib/time";

/** The sentiment vocabulary, coloured once for the whole app. */
export const SENTIMENT_COLORS: Record<string, string> = {
  POSITIVE: SEMANTIC.success,
  NEUTRAL: SERIES[8],
  NEGATIVE: SEMANTIC.danger,
  UNKNOWN: SERIES[8],
  "": SERIES[8],
};

const AXIS_LABEL = { hideOverlap: true } as const;

export function lineOverTime(data: ChartData, { area = true } = {}) {
  return {
    tooltip: { trigger: "axis" },
    legend: { show: data.series.length > 1, bottom: 0 },
    grid: { left: 8, right: 16, top: 16, bottom: data.series.length > 1 ? 32 : 8, containLabel: true },
    xAxis: {
      type: "category",
      data: data.labels.map((label) => day(label)),
      boundaryGap: false,
      axisLabel: AXIS_LABEL,
    },
    yAxis: { type: "value", minInterval: 1 },
    series: data.series.map((series, index) => ({
      name: series.name,
      type: "line",
      data: series.data,
      smooth: false,
      showSymbol: series.data.length < 40,
      areaStyle: area && index === 0 ? { opacity: 0.12 } : undefined,
      emphasis: { focus: "series" },
    })),
  };
}

export function bars(data: ChartData, { horizontal = false, color = "" } = {}) {
  const category = {
    type: "category",
    data: data.labels,
    axisLabel: horizontal ? AXIS_LABEL : { ...AXIS_LABEL, rotate: longest(data.labels) > 8 ? 30 : 0 },
  };
  const value = { type: "value", minInterval: 1 };

  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { show: data.series.length > 1, bottom: 0 },
    grid: {
      left: 8,
      right: 16,
      top: 16,
      bottom: data.series.length > 1 ? 32 : 8,
      containLabel: true,
    },
    xAxis: horizontal ? value : category,
    // A horizontal bar chart reads top-down, so the axis is reversed: the
    // biggest value belongs at the top, where the eye starts.
    yAxis: horizontal ? { ...category, inverse: true } : value,
    series: data.series.map((series) => ({
      name: series.name,
      type: "bar",
      data: series.data,
      barMaxWidth: 28,
      itemStyle: color ? { color } : undefined,
      emphasis: { focus: "series" },
    })),
  };
}

/**
 * A donut for a breakdown, with the total in the hole.
 *
 * `colorBy` maps a label to a colour when the vocabulary has meaning — that is
 * what keeps NEGATIVE red on the dashboard and red again on the record.
 */
export function donut(
  data: ChartData,
  { colors = {} as Record<string, string>, centreLabel = "" } = {},
) {
  const series = data.series[0];
  const total = (series?.data ?? []).reduce((sum, value) => sum + value, 0);

  return {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { bottom: 0, type: "scroll" },
    series: [
      {
        type: "pie",
        radius: ["58%", "80%"],
        center: ["50%", "44%"],
        avoidLabelOverlap: true,
        label: {
          show: true,
          position: "center",
          formatter: () => `{value|${total}}\n{label|${centreLabel}}`,
          rich: {
            value: { fontSize: 22, fontWeight: 600, lineHeight: 28 },
            label: { fontSize: 12, opacity: 0.7 },
          },
        },
        emphasis: { label: { show: true } },
        labelLine: { show: false },
        data: data.labels.map((label, index) => ({
          name: label || "UNKNOWN",
          value: series?.data[index] ?? 0,
          itemStyle: colors[label] ? { color: colors[label] } : undefined,
        })),
      },
    ],
  };
}

/**
 * Two series on two axes — a count and a latency, which share no unit.
 *
 * Plotting milliseconds and call counts against one axis makes whichever is
 * larger the only line with a shape.
 */
export function countAndLatency(data: ChartData) {
  const [calls, latency] = data.series;
  return {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0 },
    grid: { left: 8, right: 8, top: 16, bottom: 32, containLabel: true },
    xAxis: { type: "category", data: data.labels.map((label) => day(label)), axisLabel: AXIS_LABEL },
    yAxis: [
      { type: "value", name: calls?.name ?? "Calls", minInterval: 1 },
      { type: "value", name: latency?.name ?? "Avg ms", splitLine: { show: false } },
    ],
    series: [
      { name: calls?.name ?? "Calls", type: "bar", data: calls?.data ?? [], barMaxWidth: 24 },
      {
        name: latency?.name ?? "Avg ms",
        type: "line",
        yAxisIndex: 1,
        data: latency?.data ?? [],
        smooth: false,
      },
    ],
  };
}

function longest(labels: string[]): number {
  return labels.reduce((max, label) => Math.max(max, label.length), 0);
}

/** True when a chart has nothing to draw — the card shows an empty state. */
export function isEmpty(data: ChartData | undefined): boolean {
  if (!data) return true;
  return !data.labels.length || data.series.every((series) => series.data.every((v) => !v));
}
