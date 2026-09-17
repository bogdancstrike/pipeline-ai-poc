/**
 * Name the question you just asked.
 *
 * What is stored is the request — filters, text, the condition tree, the sort
 * — not the answer, so re-running it later asks the same question of whatever
 * has been analysed since.
 */

import { Form, Input, Modal, Switch, Typography } from "antd";
import { useEffect } from "react";

import type { RecordQuery } from "@/api/types";
import { STORAGE_KEYS } from "@/config";

export interface SaveSearchValues {
  name: string;
  description: string;
  owner: string;
  pinned: boolean;
}

export function SaveSearchModal({
  open,
  payload,
  summary,
  saving,
  onSave,
  onCancel,
}: {
  open: boolean;
  payload: RecordQuery;
  summary: string;
  saving: boolean;
  onSave: (values: SaveSearchValues) => void;
  onCancel: () => void;
}) {
  const [form] = Form.useForm<SaveSearchValues>();

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      name: "",
      description: "",
      // There is no auth yet, so "who" is remembered per browser rather than
      // proved. It is a label on a shared instance, and it says so.
      owner: localStorage.getItem(STORAGE_KEYS.owner) ?? "",
      pinned: false,
    });
  }, [open, form]);

  return (
    <Modal
      open={open}
      title="Save this search"
      okText="Save"
      confirmLoading={saving}
      onCancel={onCancel}
      onOk={() => {
        form
          .validateFields()
          .then((values) => {
            localStorage.setItem(STORAGE_KEYS.owner, values.owner ?? "");
            onSave(values);
          })
          // A failed validation rejects, and the form has already said which
          // field is wrong. Without this the rejection is unhandled, which is
          // an uncaught error in the console for something the reader can see
          // and fix on screen.
          .catch(() => undefined);
      }}
    >
      <Typography.Paragraph type="secondary">{summary}</Typography.Paragraph>
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="name"
          label="Name"
          rules={[{ required: true, message: "A saved search needs a name" }]}
        >
          <Input placeholder="Negative sentiment, people identified" autoFocus />
        </Form.Item>
        <Form.Item name="description" label="Why it is worth keeping">
          <Input.TextArea rows={2} placeholder="Optional" />
        </Form.Item>
        <Form.Item name="owner" label="Saved by" tooltip="A label on a shared instance — this app has no sign-in yet.">
          <Input placeholder="your name" />
        </Form.Item>
        <Form.Item name="pinned" label="Show first" valuePropName="checked">
          <Switch />
        </Form.Item>
      </Form>
      <input type="hidden" value={JSON.stringify(payload)} readOnly />
    </Modal>
  );
}
