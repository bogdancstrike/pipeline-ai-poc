/**
 * One record as a destination — the permalink behind the drawer.
 *
 * It adds what a drawer has no room for: the other videos that mention the
 * same entities, which is the only relatedness this data can actually prove.
 */

import { ArrowLeftOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Col, List, Row, Skeleton, Space, Tag } from "antd";
import { Link, useParams } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { PageHeader } from "@/app/AppShell";
import { RecordView } from "@/components/explorer/RecordView";

export default function RecordPage() {
  const { recordId = "" } = useParams();

  const record = useQuery({
    queryKey: ["record", recordId],
    queryFn: ({ signal }) => recordsApi.detail(recordId, signal),
  });

  const related = useQuery({
    queryKey: ["record-related", recordId],
    queryFn: ({ signal }) => recordsApi.related(recordId, signal),
    enabled: Boolean(record.data),
  });

  return (
    <div className="page">
      <PageHeader
        title={record.data?.name ?? recordId}
        blurb={record.data?.path}
        extra={
          <Link to="/records">
            <Button icon={<ArrowLeftOutlined />}>Back to records</Button>
          </Link>
        }
      />

      <Row gutter={[12, 12]}>
        <Col xs={24} xl={17}>
          {record.isPending ? (
            <Skeleton active paragraph={{ rows: 12 }} />
          ) : (
            <RecordView record={record.data} error={record.error} />
          )}
        </Col>
        <Col xs={24} xl={7}>
          <Card size="small" title="Videos sharing an entity" loading={related.isPending}>
            <List
              size="small"
              locale={{ emptyText: "No other video mentions these entities." }}
              dataSource={related.data?.items ?? []}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Link to={`/records/${encodeURIComponent(item.id)}`}>{item.name || item.id}</Link>}
                    description={
                      <Space wrap size={[4, 4]}>
                        {item.shared.slice(0, 6).map((value) => (
                          <Tag key={value}>{value}</Tag>
                        ))}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
