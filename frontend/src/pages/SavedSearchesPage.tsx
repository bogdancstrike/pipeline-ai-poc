/**
 * Questions worth asking again.
 *
 * "Run" opens the explorer with the stored question applied rather than
 * showing a stored answer: the corpus grows, and a saved search that showed
 * last week's rows would be a screenshot with a button on it.
 */

import { DeleteOutlined, PlayCircleOutlined, PushpinFilled, PushpinOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Button, Card, Empty, Input, List, Popconfirm, Space, Tag, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { savedSearchApi } from "@/api/savedSearches";
import type { SavedSearch } from "@/api/types";
import { PageHeader } from "@/app/AppShell";
import { errorText } from "@/lib/errors";
import { ago } from "@/lib/time";

export default function SavedSearchesPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [text, setText] = useState("");

  const searches = useQuery({
    queryKey: ["saved-searches", text],
    queryFn: ({ signal }) => savedSearchApi.list({ q: text, page_size: 100 }, signal),
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

  /** Put the stored question back in the URL the explorer reads. */
  const run = (search: SavedSearch) => {
    const params = new URLSearchParams();
    const payload = search.payload ?? {};
    if (payload.query_text) params.set("q", payload.query_text);
    for (const [key, value] of Object.entries(payload.filters ?? {})) {
      if (value) params.set(key, String(value));
    }
    if (payload.sort) params.set("sort", payload.sort);
    if (payload.order) params.set("order", payload.order);
    if (payload.page_size) params.set("page_size", String(payload.page_size));
    void savedSearchApi.run(search.id).catch(() => undefined);
    navigate(`/records?${params.toString()}`);
  };

  return (
    <div className="page">
      <PageHeader
        title="Saved searches"
        blurb="A stored question, not a stored answer — running one asks it again of everything analysed since."
        extra={
          <Input.Search
            allowClear
            placeholder="Find a saved search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            style={{ width: 280 }}
          />
        }
      />

      <Card size="small" loading={searches.isPending}>
        {searches.data?.items.length ? (
          <List<SavedSearch>
            dataSource={searches.data.items}
            renderItem={(search) => (
              <List.Item
                actions={[
                  <Button
                    key="run"
                    type="primary"
                    size="small"
                    icon={<PlayCircleOutlined />}
                    onClick={() => run(search)}
                  >
                    Run
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
          <Empty description="Nothing saved yet — run a search on the Records page and press Save search." />
        )}
      </Card>
    </div>
  );
}

/** The stored question in one line, so a list is readable without opening it. */
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
