/**
 * The advanced search: nested AND/OR conditions over every declared field.
 *
 * Two things make this honest rather than decorative:
 *
 * 1. **The fields come from the API.** `queryBuilderConfig` is generated from
 *    `/client/meta`, which is generated from the same `FieldSet` the SQL is
 *    built from — so the builder cannot offer a field or an operator the
 *    backend will refuse.
 * 2. **The inspector shows what will run.** `condition_text` is rendered by
 *    `client/rules.py` by walking the same tree it compiles to SQL, so the
 *    sentence a reader checks is provably the shape of the query.
 *
 * The tree is applied live — a half-typed rule is skipped server-side rather
 * than blanking the results behind the drawer.
 */

import { Alert, Button, Drawer, Space, Typography } from "antd";
import { useMemo, useState } from "react";
import {
  Builder,
  Query,
  Utils as QbUtils,
  type ImmutableTree,
  type JsonTree,
} from "@react-awesome-query-builder/antd";
import "@react-awesome-query-builder/antd/css/styles.css";

import type { FieldDescriptor, QueryNode } from "@/api/types";
import { queryBuilderConfig } from "@/components/explorer/queryBuilderConfig";
import { emptyTree } from "@/components/explorer/queryTree";

export function AdvancedSearchDrawer({
  open,
  fields,
  tree,
  conditionText,
  ruleCount,
  onApply,
  onClose,
}: {
  open: boolean;
  fields: FieldDescriptor[];
  tree: QueryNode | null;
  conditionText: string;
  ruleCount: number;
  onApply: (tree: QueryNode | null) => void;
  onClose: () => void;
}) {
  const config = useMemo(() => queryBuilderConfig(fields), [fields]);

  const [state, setState] = useState<ImmutableTree>(() =>
    QbUtils.checkTree(QbUtils.loadTree((tree ?? emptyTree()) as unknown as JsonTree), config),
  );

  const apply = () => {
    const json = QbUtils.getTree(state) as unknown as QueryNode;
    const rules = QbUtils.getTree(state) ? countRules(json) : 0;
    onApply(rules > 0 ? json : null);
    onClose();
  };

  const reset = () => {
    setState(QbUtils.checkTree(QbUtils.loadTree(emptyTree() as unknown as JsonTree), config));
  };

  return (
    <Drawer
      title="Advanced search"
      placement="right"
      width={720}
      open={open}
      onClose={onClose}
      extra={
        <Space>
          <Button onClick={reset} disabled={ruleCount === 0}>
            Clear all
          </Button>
          <Button type="primary" onClick={apply}>
            Apply
          </Button>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">
        Conditions are answered by PostgreSQL over every record, not over the page below.
        A rule you have not finished is ignored until you do.
      </Typography.Paragraph>

      <Query
        {...config}
        value={state}
        onChange={(next) => setState(next)}
        renderBuilder={(props) => (
          <div className="query-builder qb-lite">
            <Builder {...props} />
          </div>
        )}
      />

      {conditionText ? (
        <Alert
          className="query-inspector"
          type="info"
          message="What will run"
          description={<pre>{conditionText}</pre>}
        />
      ) : null}
    </Drawer>
  );
}

/** Rules in a plain JSON tree — the drawer's badge, before a round trip. */
function countRules(node: QueryNode | null | undefined): number {
  if (!node) return 0;
  if (node.type === "rule") return 1;
  const children = node.children1;
  const list = Array.isArray(children) ? children : Object.values(children ?? {});
  return list.reduce((sum, child) => sum + countRules(child), 0);
}
