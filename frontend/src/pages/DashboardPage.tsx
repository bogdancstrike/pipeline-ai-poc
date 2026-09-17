/**
 * What the corpus looks like, and how the pipeline is behaving.
 *
 * Every number here is computed in PostgreSQL over the whole window, never
 * over a page: a tile that averages 25 rows and calls itself "average
 * processing time" is a lie that looks like a metric.
 *
 * Clicking a slice or a bar navigates into the Records explorer with that
 * narrowing applied — a chart nobody can act on is decoration.
 */

import { useQuery } from "@tanstack/react-query";
import { Alert, Col, Row, Skeleton } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { dashboardApi } from "@/api/dashboard";
import { PageHeader } from "@/app/AppShell";
import { ChartCard } from "@/components/ChartCard";
import { KpiTile } from "@/components/KpiTile";
import { RangePicker } from "@/components/RangePicker";
import {
  SENTIMENT_COLORS,
  bars,
  countAndLatency,
  donut,
  lineOverTime,
} from "@/components/charts/options";
import { errorText } from "@/lib/errors";

export default function DashboardPage() {
  const [range, setRange] = useState("last_30_days");
  const navigate = useNavigate();

  const { data, isPending, error } = useQuery({
    queryKey: ["dashboard", range],
    queryFn: ({ signal }) => dashboardApi.overview({ range }, signal),
  });

  const charts = data?.charts;

  /** Open the explorer already narrowed to what was clicked. */
  const drillTo = (params: Record<string, string>) => {
    const search = new URLSearchParams(params);
    navigate(`/records?${search.toString()}`);
  };

  return (
    <div className="page">
      <PageHeader
        title="Dashboard"
        blurb="What the corpus looks like, and how the pipeline is behaving."
        extra={<RangePicker value={range} onChange={setRange} />}
      />

      {error && (
        <Alert
          type="error"
          showIcon
          message="The dashboard could not be built"
          description={errorText(error, { action: "read the records" })}
        />
      )}

      <Row gutter={[12, 12]} className="kpi-row">
        {isPending
          ? Array.from({ length: 5 }, (_, index) => (
              <Col key={index} xs={24} sm={12} lg={8} xl={4}>
                <Skeleton active paragraph={{ rows: 1 }} />
              </Col>
            ))
          : data?.kpis.map((kpi) => (
              <Col key={kpi.key} xs={24} sm={12} lg={8} xl={4}>
                <KpiTile kpi={kpi} />
              </Col>
            ))}
      </Row>

      <Row gutter={[12, 12]}>
        <Col xs={24} xl={16}>
          <ChartCard
            title="Videos analysed"
            loading={isPending}
            data={charts?.volume}
            option={lineOverTime(charts?.volume ?? { labels: [], series: [] })}
            height={300}
          />
        </Col>
        <Col xs={24} xl={8}>
          <ChartCard
            title="Sentiment"
            loading={isPending}
            data={charts?.sentiment}
            height={300}
            option={donut(charts?.sentiment ?? { labels: [], series: [] }, {
              colors: SENTIMENT_COLORS,
              centreLabel: "videos",
            })}
          />
        </Col>

        <Col xs={24} lg={12}>
          <ChartCard
            title="Entities by type"
            loading={isPending}
            data={charts?.entity_types}
            option={bars(charts?.entity_types ?? { labels: [], series: [] })}
          />
        </Col>
        <Col xs={24} lg={12}>
          <ChartCard
            title="Most-mentioned entities"
            loading={isPending}
            data={charts?.top_entities}
            option={bars(charts?.top_entities ?? { labels: [], series: [] }, { horizontal: true })}
            emptyText="No entities extracted in this window."
          />
        </Col>

        <Col xs={24} lg={12}>
          <ChartCard
            title="People most often matched"
            loading={isPending}
            data={charts?.top_persons}
            option={bars(charts?.top_persons ?? { labels: [], series: [] }, { horizontal: true })}
            emptyText="Face matching identified nobody in this window."
          />
        </Col>
        <Col xs={24} lg={12}>
          <ChartCard
            title="Average call time per service"
            extra={<span className="card-note">live calls only</span>}
            loading={isPending}
            data={charts?.service_latency}
            option={countAndLatency(charts?.service_latency ?? { labels: [], series: [] })}
            emptyText="Every call in this window was mocked."
          />
        </Col>
      </Row>

      <Row gutter={[12, 12]}>
        <Col span={24}>
          <Alert
            type="info"
            showIcon
            message="Charts are clickable"
            description="Pick a sentiment on the donut or an entity on a bar to open the explorer already narrowed to it."
            action={
              <a
                onClick={(event) => {
                  event.preventDefault();
                  drillTo({ status: "partial" });
                }}
                href="/records?status=partial"
              >
                Show partial records
              </a>
            }
          />
        </Col>
      </Row>
    </div>
  );
}
