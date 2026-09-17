/**
 * Saved searches, where the searching happens.
 *
 * They live in a drawer on the explorer rather than on a page of their own,
 * because a saved search is not a thing to look at — it is a way to get back
 * to a question. Opening one applies it to the table behind the drawer and
 * closes; a page in between would be a detour on every use.
 *
 * What is stored is the request, not the answer: filters, free text, the
 * condition tree, the sort. Running one asks the same question of whatever has
 * been analysed since.
 */

import { DeleteOutlined, PlayCircleOutlined, PushpinFilled, PushpinOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Drawer, Empty, Input, List, Popconfirm, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { savedSearchApi } from "@/api/savedSearches";
import type { RecordQuery, SavedSearch } from "@/api/types";
import { errorText } from "@/lib/errors";
import { ago } from "@/lib/time";

export function SavedSearchDrawer({
  open,
  onClose,
  onApply,
}: {
  open: boolean;
  onClose: () => void;
  onApply: (payload: RecordQuery) => void;
}) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");

  const searches = useQuery({
    queryKey: ["saved-searches", text],
    queryFn: ({ signal }) => savedSearchApi.list({ q: text, page_size: 100 }, signal),
    enabled: open,
  });

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["saved-searches"] });

  const remove = useMutation({
    mutationFn: (id: string) => savedSearchApi.remove(id),
    onSuccess: () => {
      refresh();
      message.success("Deleted");
    },
    onError: (error) => message.error(errorText(error, { action: "delete this search" })),
  });

  const pin = useMutation({
    mutationFn: (search: SavedSearch) => savedSearchApi.update(search.id, { pinned: !search.pinned }),
    onSuccess: refresh,
    onError: (error) => message.error(errorText(error, { action: "pin this search" })),
  });

  const apply = (search: SavedSearch) => {
    // Counted, so "recently used" is honest; the answer comes from the table's
    // own query, which is the one the reader is looking at.
    void savedSearchApi.run(search.id).catch(() => undefined);
    onApply(search.payload ?? {});
    onClose();
  };

  return (
    <Drawer
      title="Saved searches"
      placement="right"
      width={520}
      open={open}
      onClose={onClose}
      extra={
        <Input.Search
          allowClear
          placeholder="Find one"
          value={text}
          onChange={(event) => setText(event.target.value)}
          style={{ width: 220 }}
        />
      }
    >
      {searches.data?.items.length ? (
        <List<SavedSearch>
          loading={searches.isPending}
          dataSource={searches.data.items}
          renderItem={(search) => (
            <List.Item
              actions={[
                <Button
                  key="run"
                  type="primary"
                  size="small"
                  icon={<PlayCircleOutlined />}
                  onClick={() => apply(search)}
                >
                  Apply
                </Button>,
                <Button
                  key="pin"
                  size="small"
                  type="text"
                  aria-label={search.pinned ? "Unpin" : "Pin"}
                  icon={search.pinned ? <PushpinFilled /> : <PushpinOutlined />}
                  onClick={() => pin.mutate(search)}
                />,
                <Popconfirm
                  key="delete"
                  title="Delete this saved search?"
                  onConfirm={() => remove.mutate(search.id)}
                >
                  <Button size="small" type="text" danger aria-label="Delete" icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    {search.name}
                    {search.pinned && <Tag color="processing">pinned</Tag>}
                    {search.payload?.condition_tree ? <Tag>advanced</Tag> : null}
                  </Space>
                }
                description={
                  <Space direction="vertical" size={0}>
                    {search.description ? <span>{search.description}</span> : null}
                    <Typography.Text type="secondary">
                      {describe(search)} · {search.owner || "unattributed"} ·{" "}
                      {search.run_count} run{search.run_count === 1 ? "" : "s"}
                      {search.last_run_at ? `, last ${ago(search.last_run_at)}` : ""}
                    </Typography.Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="Nothing saved yet. Narrow the table, then press Save search."
        />
      )}
    </Drawer>
  );
}

/** The stored question in one line, so the list reads without opening each one. */
function describe(search: SavedSearch): string {
  const parts: string[] = [];
  const payload = search.payload ?? {};
  if (payload.query_text) parts.push(`text "${payload.query_text}"`);
  for (const [key, value] of Object.entries(payload.filters ?? {})) {
    if (value) parts.push(`${key}=${String(value)}`);
  }
  if (payload.condition_tree) parts.push("advanced conditions");
  return parts.length ? parts.join(" · ") : "everything";
}
