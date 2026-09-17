/**
 * The frame every screen is drawn in: a sider of places, a header of settings,
 * and a content area with the page in it.
 *
 * The one piece of logic here is the database banner. This app is the read
 * side of a pipeline that runs without it, so "no records" has two very
 * different causes — nothing has been analysed yet, or the database is down —
 * and a table that renders an empty state for the second one is lying. The
 * shell asks `/client/health` once and says which it is.
 */

import {
  ApiOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoonOutlined,
  SunOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Layout, Menu, Space, Tooltip, Typography } from "antd";
import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { metaApi } from "@/api/meta";
import { STORAGE_KEYS } from "@/config";
import { NAVIGATION, activeKey } from "@/app/navigation";
import { useAppearance } from "@/theme/AppearanceProvider";

const { Header, Sider, Content } = Layout;

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { appearance, mode, setAppearance } = useAppearance();
  const [collapsed, setCollapsed] = useState<boolean>(
    () => localStorage.getItem(STORAGE_KEYS.sidebarCollapsed) === "true",
  );

  // Polled rather than asked once: a compose stack often has the UI up before
  // PostgreSQL finished starting, and a banner that never clears would send
  // somebody looking for a problem that fixed itself 20 seconds ago.
  const health = useQuery({
    queryKey: ["client-health"],
    queryFn: ({ signal }) => metaApi.health(signal),
    refetchInterval: (query) => (query.state.data?.status === "ok" ? false : 15_000),
    retry: false,
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem(STORAGE_KEYS.sidebarCollapsed, String(next));
  };

  const degraded = health.isError || (health.data && health.data.status !== "ok");

  return (
    <Layout className="app-shell">
      <Sider
        collapsible
        collapsed={collapsed}
        trigger={null}
        width={232}
        className="app-sider"
        theme={mode === "dark" ? "dark" : "light"}
      >
        <div className="app-brand">
          <span className="app-brand-mark" aria-hidden="true" />
          {!collapsed && (
            <div className="app-brand-text">
              <strong>Video Analysis</strong>
              <span>OSINT pipeline</span>
            </div>
          )}
        </div>
        <Menu
          mode="inline"
          theme={mode === "dark" ? "dark" : "light"}
          selectedKeys={[activeKey(location.pathname)]}
          onClick={({ key }) => {
            const item = NAVIGATION.find((entry) => entry.key === key);
            if (item) navigate(item.path);
          }}
          items={NAVIGATION.map((item) => ({
            key: item.key,
            icon: item.icon,
            label: collapsed ? <Tooltip title={item.label}>{item.label}</Tooltip> : item.label,
          }))}
        />
      </Sider>

      <Layout>
        <Header className="app-header">
          <Button
            type="text"
            aria-label={collapsed ? "Expand the menu" : "Collapse the menu"}
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggle}
          />
          <Typography.Text className="app-header-title">
            {NAVIGATION.find((item) => item.key === activeKey(location.pathname))?.label}
          </Typography.Text>

          <Space size="small" className="app-header-actions">
            {health.data?.records !== undefined && (
              <Typography.Text type="secondary" className="app-header-count">
                {health.data.records.toLocaleString()} records
              </Typography.Text>
            )}
            <Tooltip title={appearance === "dark" ? "Switch to light" : "Switch to dark"}>
              <Button
                type="text"
                aria-label="Toggle dark mode"
                icon={mode === "dark" ? <SunOutlined /> : <MoonOutlined />}
                onClick={() => setAppearance(mode === "dark" ? "light" : "dark")}
              />
            </Tooltip>
            <Tooltip title="The pipeline's own API (Swagger)">
              <Button type="text" aria-label="API docs" icon={<ApiOutlined />} href="/" target="_blank" />
            </Tooltip>
          </Space>
        </Header>

        <Content className="app-content">
          {degraded && (
            <Alert
              type="warning"
              showIcon
              className="app-banner"
              message="The records database is not answering"
              description={
                <>
                  The pipeline itself is unaffected — W7 still writes every record to{" "}
                  <Typography.Text code>output/</Typography.Text>. This app will show what
                  it holds as soon as PostgreSQL is reachable
                  {health.data?.url ? (
                    <>
                      {" "}
                      at <Typography.Text code>{health.data.url}</Typography.Text>
                    </>
                  ) : null}
                  .
                </>
              }
            />
          )}
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}

/** The heading every page opens with: what this screen is, and its actions. */
export function PageHeader({
  title,
  blurb,
  extra,
}: {
  title: string;
  blurb?: string;
  extra?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <Typography.Title level={4} className="page-title">
          {title}
        </Typography.Title>
        {blurb && (
          <Typography.Text type="secondary" className="page-blurb">
            {blurb}
          </Typography.Text>
        )}
      </div>
      {extra ? <Space wrap>{extra}</Space> : null}
    </div>
  );
}

export { Link };
