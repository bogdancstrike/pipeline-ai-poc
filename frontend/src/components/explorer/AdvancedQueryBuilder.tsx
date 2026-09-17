/**
 * The nested condition editor of §4 — `CONDITION AND ( CONDITION OR … )`.
 *
 * Two things here are less obvious than they look.
 *
 * **The tree is owned locally while it is being edited.** The page keeps the
 * question in the URL so it can be shared and reloaded, which means every
 * change comes straight back as a new `value`. Re-loading the editor from that
 * echo is what made "Add rule" appear to do nothing: a rule with no field yet
 * is an *empty* rule, the library discards empty rules when a tree is loaded,
 * and the new row vanished between the click and the next render. So the
 * component compares an incoming `value` against what it last emitted and only
 * reloads when somebody else — a saved search, the back button — changed it.
 *
 * **A half-built rule is not an error.** `compile_tree` skips incomplete rules
 * by design, so the results behind the drawer keep answering the part of the
 * question that is finished instead of blanking on every keystroke.
 */

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  Builder,
  Query,
  Utils as QbUtils,
  type ImmutableTree,
  type ItemBuilderProps,
  type JsonTree,
} from "@react-awesome-query-builder/antd";
import { Button, Tooltip } from "antd";
import { CopyOutlined } from "@ant-design/icons";
import "@react-awesome-query-builder/antd/css/styles.css";

import type { FieldDescriptor as ExplorerField } from "@/api/types";

import { queryBuilderConfig } from "@/components/explorer/queryBuilderConfig";
import { duplicateNode, emptyTree, type QueryNode } from "@/components/explorer/queryTree";

export interface AdvancedQueryBuilderProps {
  /** The catalogue the API published for the selected dataset. */
  fields: ExplorerField[];
  value: QueryNode | null;
  onChange: (tree: QueryNode) => void;
}

export function AdvancedQueryBuilder({ fields, value, onChange }: AdvancedQueryBuilderProps) {
  const config = useMemo(() => queryBuilderConfig(fields), [fields]);
  const [tree, setTree] = useState<ImmutableTree>(() => load(value));

  /** The JSON of the last tree handed upward; an equal `value` is our own echo. */
  const emitted = useRef(serialise(value));

  useEffect(() => {
    const incoming = serialise(value);
    if (incoming === emitted.current) return;
    emitted.current = incoming;
    setTree(load(value));
  }, [value]);

  const publish = (next: ImmutableTree) => {
    setTree(next);
    const json = QbUtils.getTree(next) as unknown as QueryNode;
    emitted.current = serialise(json);
    onChange(json);
  };

  /** Clone one rule or group in place, keyed by the path the builder gives us. */
  const duplicate = (path: readonly string[]) => {
    const current = QbUtils.getTree(tree) as unknown as QueryNode;
    const next = duplicateNode(current, path);
    if (next) publish(QbUtils.loadTree(next as unknown as JsonTree));
  };

  return (
    <div className="nu-query-builder" aria-label="Advanced query builder">
      <Query
        {...config}
        settings={{
          ...config.settings,
          // The library renders the rule's own action bar and gives no room to
          // extend it, so the duplicate control is attached by wrapping each
          // item — the one place a path to the node is available.
          renderItem: (props: ItemBuilderProps) => (
            <QueryItem {...props} onDuplicate={duplicate} />
          ),
        }}
        value={tree}
        onChange={publish}
        // The library's stylesheet is scoped under `.query-builder`, and it is
        // the host application that has to render it — without this wrapper
        // every rule falls back to unstyled stacked blocks.
        renderBuilder={(props) => (
          <div className="query-builder">
            <Builder {...props} />
          </div>
        )}
      />
    </div>
  );
}

/**
 * One rule or group, plus the duplicate action §4 asks for beside it.
 *
 * `itemComponent` is the library's own renderer for this node; wrapping rather
 * than replacing it means the rule keeps every behaviour — drag handles,
 * validation, locking — that the builder gives it.
 */
function QueryItem({
  itemComponent: Item,
  onDuplicate,
  ...props
}: ItemBuilderProps & { onDuplicate: (path: readonly string[]) => void }) {
  const path: string[] = props.path?.toJS?.() ?? [];
  const isRoot = path.length <= 1;

  // A fragment, not a wrapper element: the library's stylesheet lays a rule out
  // through the parent container's own children, and an extra box between them
  // collapses the row into a stack.
  return (
    <Fragment>
      {Item(props)}
      {!isRoot && (
        <Tooltip title="Duplicate">
          <Button
            className="nu-query-duplicate"
            type="text"
            size="small"
            icon={<CopyOutlined />}
            aria-label={`Duplicate this ${props.type === "group" ? "group" : "rule"}`}
            onClick={() => onDuplicate(path)}
          />
        </Tooltip>
      )}
    </Fragment>
  );
}

function load(value: QueryNode | null): ImmutableTree {
  return QbUtils.loadTree((value ?? emptyTree()) as unknown as JsonTree);
}

function serialise(value: QueryNode | null | undefined): string {
  return JSON.stringify(value ?? null);
}
