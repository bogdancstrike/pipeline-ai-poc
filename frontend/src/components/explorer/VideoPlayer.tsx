/**
 * The video itself, beside its analysis.
 *
 * The pipeline never opens the file — it forwards a path and the AI services
 * resolve it on their own filesystem. So the player is only rendered when the
 * API says the same file is *also* readable from the pipeline container
 * (`video.playable`, i.e. it resolved under VIDEO_SEARCH_DIRS). When it is not,
 * the panel says why and shows the path, which is more use than a black
 * rectangle that never starts.
 */

import { Alert, Typography } from "antd";

import type { RecordDetail } from "@/api/types";

export function VideoPlayer({ record }: { record: RecordDetail }) {
  const video = record.video;

  if (!video?.playable || !video.url) {
    return (
      <Alert
        type="info"
        showIcon
        message="This video cannot be played here"
        description={
          <>
            The AI services opened it on their own host. To watch it in the browser, mount the
            same file under one of <Typography.Text code>VIDEO_SEARCH_DIRS</Typography.Text> —
            in compose that is <Typography.Text code>./videos</Typography.Text> →{" "}
            <Typography.Text code>/app/videos</Typography.Text>.
            <br />
            <Typography.Text type="secondary" copyable>
              {record.path}
            </Typography.Text>
          </>
        }
      />
    );
  }

  return (
    <div className="record-player">
      {/* `key` on the id: swapping records in the drawer must load the new
          file rather than keep the previous one's buffered stream. */}
      <video key={record.id} src={video.url} controls preload="metadata" playsInline />
    </div>
  );
}
