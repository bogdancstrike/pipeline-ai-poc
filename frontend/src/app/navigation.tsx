/**
 * The one list of places this app has.
 *
 * The sider, the command palette that may follow and the document title all
 * read it, so a route added in one place cannot be missing from the others.
 */

import {
  BarChartOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  SaveOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";

export interface NavItem {
  key: string;
  path: string;
  label: string;
  icon: ReactNode;
  /** What this screen is for, one line — the sider tooltip and the page head. */
  blurb: string;
}

export const NAVIGATION: NavItem[] = [
  {
    key: "dashboard",
    path: "/",
    label: "Dashboard",
    icon: <DashboardOutlined />,
    blurb: "What the corpus looks like, and how the pipeline is behaving.",
  },
  {
    key: "explorer",
    path: "/records",
    label: "Records",
    icon: <VideoCameraOutlined />,
    blurb: "Every analysed video, searchable across summary, transcript and OCR.",
  },
  {
    key: "searches",
    path: "/searches",
    label: "Saved searches",
    icon: <SaveOutlined />,
    blurb: "Questions worth asking again.",
  },
  {
    key: "statistics",
    path: "/statistics",
    label: "Statistics",
    icon: <BarChartOutlined />,
    blurb: "Per-service call counts, latency and failures.",
  },
  {
    key: "pipeline",
    path: "/pipeline",
    label: "Pipeline",
    icon: <DatabaseOutlined />,
    blurb: "The wiring behind the records: services, prompts, mock switches.",
  },
];

/** The nav entry a path belongs to — longest match wins, so /records/x is Records. */
export function activeKey(pathname: string): string {
  const match = [...NAVIGATION]
    .sort((a, b) => b.path.length - a.path.length)
    .find((item) => (item.path === "/" ? pathname === "/" : pathname.startsWith(item.path)));
  return match?.key ?? "dashboard";
}
