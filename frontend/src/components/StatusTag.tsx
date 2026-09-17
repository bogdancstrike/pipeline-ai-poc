import { Tag, Tooltip } from "antd";

/**
 * `analysed` or `partial`, and what partial cost.
 *
 * A record is written whichever it is — `AI_FAIL_FAST=false` means a failing
 * service is recorded on its branch and the pipeline completes — so a table
 * that did not distinguish them would invite reading a half-answer as a whole
 * one.
 */
export function StatusTag({ status, errors }: { status: string; errors?: number }) {
  if (status === "partial") {
    return (
      <Tooltip title={errors ? `${errors} service(s) did not answer` : "A service did not answer"}>
        <Tag color="warning">partial</Tag>
      </Tooltip>
    );
  }
  return <Tag color="success">analysed</Tag>;
}
