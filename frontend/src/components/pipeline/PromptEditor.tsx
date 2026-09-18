/**
 * Edit the three prompts, from the browser.
 *
 * What is being edited is the text posted to :8825 as `prompt_text` — the whole
 * file, not a template with holes in it. So the editor is a plain textarea with
 * a monospace face and no cleverness: the thing on screen is byte-for-byte the
 * thing the model receives.
 *
 * Three honesties the UI owes the reader:
 *
 *   * **Unsaved text is marked**, because a prompt left half-edited in a tab
 *     is otherwise indistinguishable from one that is live.
 *   * **"Modified" is shown against the shipped wording**, so it is always
 *     clear whether the running prompt is the one in the repository.
 *   * **Reset is offered per prompt**, and it restores the file's text rather
 *     than the last save — the file is the default this project ships.
 *
 * The page owns the heading and the one-line explanation; this owns the
 * editing. It renders no card of its own, so three sections down the page are
 * three headings rather than three boxes.
 */

import { ReloadOutlined, SaveOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Alert, Badge, Button, Input, Popconfirm, Skeleton, Space, Tabs, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { promptsApi, type PromptRow } from "@/api/prompts";
import { STORAGE_KEYS } from "@/config";
import { errorText } from "@/lib/errors";
import { ago } from "@/lib/time";

export function PromptEditor() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const prompts = useQuery({
    queryKey: ["prompts"],
    queryFn: ({ signal }) => promptsApi.list(signal),
  });

  // Seed a draft per prompt the first time its text arrives, and leave it
  // alone afterwards: refetching must not discard what somebody is typing.
  useEffect(() => {
    if (!prompts.data) return;
    setDrafts((current) => {
      const next = { ...current };
      for (const item of prompts.data.items) {
        if (!(item.name in next)) next[item.name] = item.text;
      }
      return next;
    });
  }, [prompts.data]);

  const save = useMutation({
    mutationFn: ({ name, text }: { name: string; text: string }) =>
      promptsApi.save(name, text, localStorage.getItem(STORAGE_KEYS.owner) ?? ""),
    onSuccess: (row) => {
      void queryClient.invalidateQueries({ queryKey: ["prompts"] });
      message.success(`${row.name} saved as v${row.version} — the next video uses it`);
    },
    onError: (error) => message.error(errorText(error, { action: "save this prompt" })),
  });

  const reset = useMutation({
    mutationFn: (name: string) => promptsApi.reset(name),
    onSuccess: (row) => {
      setDrafts((current) => ({ ...current, [row.name]: row.text }));
      void queryClient.invalidateQueries({ queryKey: ["prompts"] });
      message.success(`${row.name} restored to the wording that ships`);
    },
    onError: (error) => message.error(errorText(error, { action: "reset this prompt" })),
  });

  if (prompts.isPending) return <Skeleton active paragraph={{ rows: 6 }} />;

  const items = prompts.data?.items ?? [];

  return (
    <div className="prompt-editor">
      {prompts.error && (
        <Alert
          type="error"
          showIcon
          message="The prompts could not be read"
          description={errorText(prompts.error, { action: "read the prompts" })}
        />
      )}

      {/* The one thing that makes every edit below pointless, said once. */}
      {prompts.data && !prompts.data.from_db && (
        <Alert
          type="warning"
          showIcon
          message={`PROMPTS_FROM_DB is off — the files in ${prompts.data.dir} are in use, and saving here changes nothing.`}
        />
      )}

      <Tabs
        items={items.map((item) => ({
          key: item.name,
          label: <PromptTabLabel item={item} dirty={(drafts[item.name] ?? item.text) !== item.text} />,
          children: (
            <PromptPane
              item={item}
              draft={drafts[item.name] ?? item.text}
              saving={save.isPending}
              resetting={reset.isPending}
              onChange={(text) => setDrafts((current) => ({ ...current, [item.name]: text }))}
              onSave={(text) => save.mutate({ name: item.name, text })}
              onReset={() => reset.mutate(item.name)}
            />
          ),
        }))}
      />
    </div>
  );
}

function PromptTabLabel({ item, dirty }: { item: PromptRow; dirty: boolean }) {
  return (
    <Space size={6}>
      {dirty ? <Badge status="processing" /> : null}
      {item.name}
      {item.modified ? <Tag color="processing">edited</Tag> : null}
    </Space>
  );
}

function PromptPane({
  item,
  draft,
  saving,
  resetting,
  onChange,
  onSave,
  onReset,
}: {
  item: PromptRow;
  draft: string;
  saving: boolean;
  resetting: boolean;
  onChange: (text: string) => void;
  onSave: (text: string) => void;
  onReset: () => void;
}) {
  const dirty = draft !== item.text;

  return (
    <div className="prompt-pane">
      <Input.TextArea
        value={draft}
        onChange={(event) => onChange(event.target.value)}
        autoSize={{ minRows: 10, maxRows: 24 }}
        spellCheck={false}
        className="prompt-textarea"
        aria-label={`The ${item.name} prompt`}
      />

      {/* The provenance and the verbs on one line: what this text is, and what
          can be done to it. Two rows for six words is what made this crowded. */}
      <div className="prompt-actions">
        <Typography.Text type="secondary" className="prompt-meta">
          {item.file} · {draft.length.toLocaleString()} chars
          {item.version ? ` · v${item.version}` : ""}
          {item.updated_at ? ` · saved ${ago(item.updated_at)}` : " · never saved"}
          {item.updated_by ? ` by ${item.updated_by}` : ""}
          {dirty ? " · unsaved changes" : ""}
        </Typography.Text>

        <Space>
          <Button disabled={!dirty} onClick={() => onChange(item.text)}>
            Discard
          </Button>
          <Popconfirm
            title="Restore the wording that ships?"
            description="The text in src/prompts/ replaces what is stored."
            onConfirm={onReset}
          >
            <Button icon={<ReloadOutlined />} loading={resetting} disabled={!item.modified}>
              Reset to shipped
            </Button>
          </Popconfirm>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!dirty || !draft.trim()}
            onClick={() => onSave(draft)}
          >
            Save
          </Button>
        </Space>
      </div>
    </div>
  );
}
