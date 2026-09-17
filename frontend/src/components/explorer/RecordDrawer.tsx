/**
 * One record, without leaving the list.
 *
 * A drawer rather than a navigation, because scanning a result set means
 * opening ten of them: a round trip through a page and back loses the scroll
 * position and the reader's place in the list. The permalink is still there
 * for when the record itself is the destination.
 */

import { ExportOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Drawer, Skeleton, Space } from "antd";
import { Link } from "react-router-dom";

import { recordsApi } from "@/api/records";
import { RecordView } from "@/components/explorer/RecordView";

export function RecordDrawer({
  recordId,
  onClose,
}: {
  recordId: string | null;
  onClose: () => void;
}) {
  const { data, isPending, error } = useQuery({
    queryKey: ["record", recordId],
    queryFn: ({ signal }) => recordsApi.detail(recordId as string, signal),
    enabled: Boolean(recordId),
  });

  return (
    <Drawer
      title={data?.name ?? "Record"}
      placement="right"
      width={820}
      open={Boolean(recordId)}
      onClose={onClose}
      extra={
        recordId ? (
          <Space>
            <Link to={`/records/${encodeURIComponent(recordId)}`}>
              <Button icon={<ExportOutlined />}>Open as a page</Button>
            </Link>
          </Space>
        ) : null
      }
    >
      {isPending && recordId ? (
        <Skeleton active paragraph={{ rows: 10 }} />
      ) : (
        <RecordView record={data} error={error} />
      )}
    </Drawer>
  );
}
