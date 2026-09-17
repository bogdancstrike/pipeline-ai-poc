/**
 * Plain-JSON operations on a query-builder tree.
 *
 * The builder's own state is an Immutable.js structure, but the tree that
 * travels — into the URL, into a saved search, into the request body — is the
 * JSON one. Working here keeps those operations testable without a React tree
 * and without depending on the library's internal shape beyond the two keys it
 * documents: `children1` and `properties`.
 */

import type { QueryNode } from "@/api/types";

export type { QueryNode };

/** A fresh, empty root group — an AND of nothing, which matches everything. */
export function emptyTree(): QueryNode {
  return {
    id: newId(),
    type: "group",
    children1: {},
    properties: { conjunction: "AND", not: false },
  };
}

/** True when the tree carries no rules at all, however deeply nested. */
export function isEmptyTree(tree: QueryNode | null | undefined): boolean {
  return countRules(tree) === 0;
}

/** How many rules the tree holds, complete or not. */
export function countRules(tree: QueryNode | null | undefined): number {
  if (!tree) return 0;
  if (tree.type === "rule") return 1;
  return childrenOf(tree).reduce((total, child) => total + countRules(child), 0);
}

/**
 * Insert a copy of the node at `path` directly after it.
 *
 * `path` is the chain of node ids from the root, which is what the builder
 * hands to a custom item renderer. Every id in the copy is regenerated: two
 * nodes sharing an id makes the builder edit both at once.
 *
 * Returns a new tree, or `null` when the path does not resolve — a stale path
 * from a tree that changed under the click, which is a no-op rather than a crash.
 */
export function duplicateNode(tree: QueryNode, path: readonly string[]): QueryNode | null {
  // The first path segment is the root itself; the root cannot be duplicated.
  const trail = path.slice(1);
  if (trail.length === 0) return null;

  const copy = structuredClone(tree);
  let parent: QueryNode = copy;
  for (const id of trail.slice(0, -1)) {
    const next = childMap(parent)[id];
    if (!next) return null;
    parent = next;
  }

  const targetId = trail[trail.length - 1] as string;
  const children = childMap(parent);
  const original = children[targetId];
  if (!original) return null;

  // Rebuilt rather than mutated so the copy lands next to its original: an
  // object's key order is its render order in the builder.
  const rebuilt: Record<string, QueryNode> = {};
  for (const [id, child] of Object.entries(children)) {
    rebuilt[id] = child;
    if (id === targetId) {
      const clone = withFreshIds(structuredClone(original));
      rebuilt[clone.id as string] = clone;
    }
  }
  parent.children1 = rebuilt;
  return copy;
}

/** The node's children as an id-keyed map, whichever shape they arrived in. */
function childMap(node: QueryNode): Record<string, QueryNode> {
  const children = node.children1;
  if (!children) return {};
  if (Array.isArray(children)) {
    return Object.fromEntries(
      children.map((child, index) => [child.id ?? String(index), child] as const),
    );
  }
  return children;
}

function childrenOf(node: QueryNode): QueryNode[] {
  return Object.values(childMap(node));
}

function withFreshIds(node: QueryNode): QueryNode {
  node.id = newId();
  const children = node.children1;
  if (children) {
    node.children1 = Object.fromEntries(
      Object.values(Array.isArray(children) ? children : Object.values(children))
        .map((child) => withFreshIds(child))
        .map((child) => [child.id as string, child] as const),
    );
  }
  return node;
}

function newId(): string {
  return crypto.randomUUID();
}
