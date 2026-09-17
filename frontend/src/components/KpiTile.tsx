/**
 * One number, what it was, and whether that is good news.
 *
 * The direction is declared per metric by the API (`better: "up" | "down"`),
 * because the tile cannot know: more videos analysed is good, more partial
 * records is not, and colouring both green for "up" is how a dashboard teaches
 * people to ignore it.
 */

import { ArrowDownOutlined, ArrowUpOutlined, MinusOutlined } from "@ant-design/icons";
import { Card, Statistic, Tooltip, Typography } from "antd";

import type { Kpi } from "@/api/types";
import { formatNumber } from "@/lib/formats";

export function KpiTile({ kpi, loading }: { kpi: Kpi; loading?: boolean }) {
  const rising = kpi.delta > 0;
  const flat = kpi.delta === 0;
  const good = flat ? null : (kpi.better === "up") === rising;

  const tone = good === null ? "secondary" : good ? "success" : "danger";
  const Icon = flat ? MinusOutlined : rising ? ArrowUpOutlined : ArrowDownOutlined;

  return (
    <Card size="small" className="kpi-tile" loading={loading}>
      <Statistic
        title={kpi.label}
        value={kpi.value}
        suffix={kpi.unit}
        formatter={(value) => formatNumber(Number(value), { maximumFractionDigits: 2 })}
      />
      <Tooltip title={`Previous period: ${formatNumber(kpi.previous, { maximumFractionDigits: 2 })}${kpi.unit}`}>
        <Typography.Text type={tone as "secondary" | "success" | "danger"} className="kpi-delta">
          <Icon />{" "}
          {flat
            ? "no change"
            : `${rising ? "+" : ""}${formatNumber(kpi.delta, { maximumFractionDigits: 2 })}${kpi.unit}`}
          {kpi.delta_pct === null ? "" : ` (${kpi.delta_pct > 0 ? "+" : ""}${kpi.delta_pct}%)`}
        </Typography.Text>
      </Tooltip>
    </Card>
  );
}
