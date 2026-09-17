/**
 * The last line of defence: a component that throws while rendering takes its
 * screen down, not the shell around it.
 *
 * It carries the correlation id of the most recent failed request, because the
 * component that throws while rendering a bad response reaches here with a
 * `TypeError` and no way back to the call that supplied the value — and almost
 * always, that call is the one that just failed.
 */

import { Button, Result, Typography } from "antd";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { lastFailedCorrelationId } from "@/api/client";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ui] render failed", error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    const correlationId = lastFailedCorrelationId();
    return (
      <Result
        status="error"
        title="This screen stopped"
        subTitle={
          <span>
            {error.message}
            {correlationId ? (
              <>
                {" · "}
                <Typography.Text code copyable>
                  {correlationId}
                </Typography.Text>
              </>
            ) : null}
          </span>
        }
        extra={
          <Button type="primary" onClick={() => this.setState({ error: null })}>
            Try again
          </Button>
        }
      />
    );
  }
}
