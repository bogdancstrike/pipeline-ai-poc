/**
 * Submit a video to the pipeline.
 *
 * The path is the AI host's path, not this machine's — the services resolve it
 * on their own filesystem, which is why a typo produces "path does not exist"
 * from :8821 rather than a 400 here. The field says so, because that is the
 * single most common way a run fails.
 *
 * Submitting returns as soon as the message is on `video.in`. The record shows
 * up in the explorer when W7 has written it, so the modal says what to expect
 * rather than pretending the work is done.
 */

import { useMutation } from "@tanstack/react-query";
import { Alert, Form, Input, Modal, Select, Typography } from "antd";

import { pipelineApi, type AnalyzeRequest } from "@/api/pipeline";
import { errorText } from "@/lib/errors";

interface FormValues {
  path: string;
  id?: string;
  language?: string;
  task?: string;
}

export function AnalyzeModal({
  open,
  onClose,
  onSubmitted,
}: {
  open: boolean;
  onClose: () => void;
  onSubmitted: (id: string) => void;
}) {
  const [form] = Form.useForm<FormValues>();

  const submit = useMutation({
    mutationFn: (values: FormValues) => {
      const body: AnalyzeRequest = { path: values.path.trim() };
      if (values.id?.trim()) body.id = values.id.trim();
      // Only the transcribe overrides actually chosen; the rest fall back to
      // .env, which is where the defaults are documented.
      const options: Record<string, unknown> = {};
      if (values.language) options["language"] = values.language;
      if (values.task) options["task"] = values.task;
      if (Object.keys(options).length) body.options = options;
      return pipelineApi.analyze(body);
    },
    onSuccess: (answer) => {
      form.resetFields();
      onSubmitted(String(answer.id ?? ""));
      onClose();
    },
  });

  return (
    <Modal
      open={open}
      title="Analyse a video"
      okText="Submit"
      confirmLoading={submit.isPending}
      onCancel={onClose}
      onOk={() => form.validateFields().then((values) => submit.mutate(values))}
    >
      <Typography.Paragraph type="secondary">
        The message goes on <Typography.Text code>video.in</Typography.Text> and the seven
        workers take it from there. The record appears here once W7 has written it.
      </Typography.Paragraph>

      {submit.error && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message="The pipeline refused the submission"
          description={errorText(submit.error, { action: "submit this video" })}
        />
      )}

      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="path"
          label="Video path"
          tooltip="As the AI services (8821-8825) will open it, on their own filesystem."
          rules={[{ required: true, message: "The pipeline needs a path" }]}
        >
          <Input placeholder="/video/migrants.mp4" autoFocus />
        </Form.Item>
        <Form.Item
          name="id"
          label="Run id"
          tooltip="Both aggregators group their branches by it, so it must be unique. Generated when left empty."
        >
          <Input placeholder="generated" />
        </Form.Item>
        <Form.Item name="language" label="Transcribe language" tooltip="Overrides TRANSCRIBE_LANGUAGE for this run.">
          <Select
            allowClear
            placeholder="from .env"
            options={[
              { value: "ar", label: "Arabic (ar)" },
              { value: "en", label: "English (en)" },
              { value: "es", label: "Spanish (es)" },
              { value: "ro", label: "Romanian (ro)" },
            ]}
          />
        </Form.Item>
        <Form.Item name="task" label="Transcribe task">
          <Select
            allowClear
            placeholder="from .env"
            options={[
              { value: "translate", label: "translate — into English" },
              { value: "transcribe", label: "transcribe — original language" },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
