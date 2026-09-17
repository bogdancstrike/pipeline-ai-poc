/**
 * A chart in a card, with the two states a chart actually has besides "drawn":
 * still loading, and nothing to draw.
 *
 * The empty state matters more than it looks. A chart with no data renders as
 * an empty grid, which reads as "zero" rather than "nothing has been analysed
 * in this window" — two very different messages on a fresh install.
 */

import { Card, Empty, Skeleton } from "antd";
import type { ReactNode } from "react";

import { Chart } from "@/components/charts/Chart";
import type { ChartData } from "@/api/types";
import { isEmpty } from "@/components/charts/options";

export function ChartCard({
  title,
  extra,
  data,
  option,
  height = 280,
  loading,
  emptyText = "Nothing analysed in this window yet.",
}: {
  title: string;
  extra?: ReactNode;
  data?: ChartData;
  option: Record<string, unknown>;
  height?: number;
  loading?: boolean;
  emptyText?: string;
}) {
  return (
    <Card size="small" title={title} extra={extra} className="chart-card">
      {loading ? (
        <Skeleton active paragraph={{ rows: 5 }} />
      ) : isEmpty(data) ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} style={{ height }} />
      ) : (
        <Chart option={option} height={height} label={title} />
      )}
    </Card>
  );
}
