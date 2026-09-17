/**
 * The bridge between the backend field catalogue and the query builder.
 *
 * `core/query.py` publishes, per field, the operators PostgreSQL will actually
 * honour for that column's kind. react-awesome-query-builder names the same
 * operators differently, and — the part that matters — accepts a *different
 * set of names per widget type*: `is_empty` exists for text and nowhere else,
 * a select uses `select_equals` where text uses `equal`, and offering an
 * operator a type does not define leaves the rule with an empty operator
 * dropdown and no way to finish it.
 *
 * So the translation is per kind, not global, and it is a total function: every
 * operator the backend allows for a kind maps to one the builder can render,
 * and every operator the builder can emit maps back through
 * `OPERATOR_ALIASES` in `core/query.py`. `queryBuilderConfig.test.ts` asserts
 * both halves against the vocabulary the API publishes, so adding an operator
 * on either side without the other fails the build rather than a user's query.
 */

import { Tooltip } from "antd";
import { createElement, type ReactElement } from "react";
import { AntdConfig } from "@react-awesome-query-builder/antd";
import type { Config, Operators, Type, Types } from "@react-awesome-query-builder/antd";

import type { FieldDescriptor as ExplorerField, FieldKind } from "@/api/types";

/** The builder type each backend field kind is edited as. */
export const BUILDER_TYPE: Record<FieldKind, string> = {
  text: "text",
  // Compared as text server-side; the widget is a plain input either way.
  uuid: "text",
  json: "text",
  array: "text",
  enum: "select",
  bool: "boolean",
  number: "number",
  datetime: "datetime",
};

/**
 * "Has no value" is spelled `is_empty` for text and `is_null` everywhere else.
 * Both reach `empty`/`not_empty` in `core/query.py`, which treats NULL and the
 * empty string as the same absence, so `exists` collapses onto `not_empty`.
 */
const PRESENCE_AS_EMPTY = {
  empty: "is_empty",
  not_empty: "is_not_empty",
  exists: "is_not_empty",
  not_exists: "is_empty",
} as const;

const PRESENCE_AS_NULL = {
  empty: "is_null",
  not_empty: "is_not_null",
  exists: "is_not_null",
  not_exists: "is_null",
} as const;

const EQUALITY = { eq: "equal", ne: "not_equal" } as const;

/** `before`/`after` are the date spelling of `lt`/`gt`; one widget serves both. */
const ORDERING = {
  gt: "greater",
  after: "greater",
  gte: "greater_or_equal",
  lt: "less",
  before: "less",
  lte: "less_or_equal",
  between: "between",
} as const;

const MEMBERSHIP = { in: "select_any_in", not_in: "select_not_any_in" } as const;

/** Backend operator → builder operator, per builder type. */
const OPERATOR_BY_TYPE: Record<string, Record<string, string>> = {
  text: {
    ...EQUALITY,
    contains: "like",
    not: "not_like",
    starts: "starts_with",
    ends: "ends_with",
    ...MEMBERSHIP,
    ...PRESENCE_AS_EMPTY,
  },
  select: {
    eq: "select_equals",
    ne: "select_not_equals",
    ...MEMBERSHIP,
    ...PRESENCE_AS_NULL,
  },
  boolean: { ...EQUALITY, ...PRESENCE_AS_NULL },
  number: { ...EQUALITY, ...ORDERING, ...MEMBERSHIP, ...PRESENCE_AS_NULL },
  datetime: { ...EQUALITY, ...ORDERING, ...PRESENCE_AS_NULL },
};

/**
 * The builder operator for one backend operator on one field kind, or
 * `undefined` when the pairing has no equivalent — which the catalogue should
 * never produce, and the contract test asserts it does not.
 */
export function builderOperator(kind: FieldKind, operator: string): string | undefined {
  return OPERATOR_BY_TYPE[BUILDER_TYPE[kind]]?.[operator];
}

/** The builder operators offered for a field, in the catalogue's order. */
export function builderOperators(field: ExplorerField): string[] {
  const mapped = field.operators
    .map((operator) => builderOperator(field.kind, operator))
    .filter((operator): operator is string => Boolean(operator));
  // `before`/`after` collapse onto `less`/`greater`, and `exists` onto
  // `is_not_empty`; the dropdown must list each choice once.
  return [...new Set(mapped)];
}

/**
 * The words the operator dropdown shows.
 *
 * Deliberately the same vocabulary `_TEXT_OPERATOR` in `core/rules.py` uses to
 * render the query inspector, so the sentence a reader builds in the dropdown
 * is the sentence the inspector reads back. The library's defaults ("==",
 * "Any in") would make those two descriptions of one query look unrelated.
 */
const OPERATOR_LABEL: Record<string, string> = {
  equal: "=",
  not_equal: "\u2260",
  select_equals: "=",
  select_not_equals: "\u2260",
  less: "<",
  less_or_equal: "\u2264",
  greater: ">",
  greater_or_equal: "\u2265",
  like: "contains",
  not_like: "does not contain",
  starts_with: "starts with",
  ends_with: "ends with",
  between: "between",
  select_any_in: "in",
  select_not_any_in: "not in",
  // NULL and the empty string are one absence to `core/query.py`, so the two
  // spellings of the presence test get one pair of words.
  is_empty: "is empty",
  is_not_empty: "is not empty",
  is_null: "is empty",
  is_not_null: "is not empty",
};

function builderOperatorDefinitions(): Operators {
  const operators = AntdConfig.operators;
  return Object.fromEntries(
    Object.entries(operators).map(([name, definition]) => [
      name,
      name in OPERATOR_LABEL
        ? { ...definition, label: OPERATOR_LABEL[name] as string }
        : definition,
    ]),
  );
}

/**
 * `select_any_in` belongs to the multiselect widget, which text and number
 * types do not carry by default — yet `?name__in=a,b` and `?score__in=1,2` are
 * both filters the backend accepts. Lending those types the widget keeps the
 * builder's reach equal to the API's instead of quietly narrower.
 */
function withMembershipWidget(type: Type): Type {
  return {
    ...type,
    widgets: {
      ...type.widgets,
      multiselect: {
        ...type.widgets?.["multiselect"],
        operators: [...Object.values(MEMBERSHIP)],
      },
    },
  };
}

function builderTypes(): Types {
  const types = AntdConfig.types;
  return {
    ...types,
    text: withMembershipWidget(types["text"]),
    number: withMembershipWidget(types["number"]),
  };
}

function fieldSettings(field: ExplorerField): Record<string, unknown> {
  if (field.kind === "enum") {
    return {
      listValues: field.choices.map((value) => ({ value, title: humanise(value) })),
      // A facet with no declared vocabulary still has to be filterable.
      allowCustomValues: field.choices.length === 0,
      showSearch: true,
    };
  }
  // Free-text and numeric "is one of" lists are typed, not picked, so the
  // multiselect widget runs in tag mode with no options behind it.
  return { listValues: [], allowCustomValues: true };
}

/** `IN_PROGRESS` is a database value; `In progress` is what a person reads. */
function humanise(value: string): string {
  const spaced = value.replaceAll("_", " ").toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * What each of the library's own buttons is for, in the reader's words.
 *
 * Keyed on the type the library asks for, so a control it grows tomorrow
 * appears with its own label rather than silently unlabelled.
 */
const BUTTON_HELP: Record<string, { title: string; name: string }> = {
  addRule: {
    title: "One condition — a field, a comparison and a value",
    name: "Add a rule",
  },
  addGroup: {
    title: "A bracket. Rules inside it are answered together, then compared with the rest",
    name: "Add a group",
  },
  addSubRule: { title: "A condition inside this group", name: "Add a rule here" },
  addSubRuleSimple: { title: "A condition inside this group", name: "Add a rule here" },
  addSubGroup: { title: "A bracket inside this one", name: "Add a group here" },
  delRule: { title: "Remove this rule", name: "Remove this rule" },
  delGroup: { title: "Remove this group and everything in it", name: "Remove this group" },
  delRuleGroup: { title: "Remove this group and everything in it", name: "Remove this group" },
};

/**
 * The library's buttons, with a name and a tooltip.
 *
 * The delete controls are icons the library renders with *no* text at all — so
 * a screen reader announced "button" and a pointer got nothing on hover, which
 * is how the editor came to have two adjacent circles nobody could tell apart.
 * Wrapping rather than replacing keeps every behaviour the library gives them.
 */
type ButtonFactory = NonNullable<typeof AntdConfig.settings.renderButton>;

/**
 * The library types this as returning *its own* button element, and a tooltip
 * wrapping one is a different element type. The cast is at the boundary and
 * only here: what the library does with the result is render it.
 */
const renderLabelledButton = ((props, ctx) => {
  const type = String(props.type ?? "");
  const help = BUTTON_HELP[type];
  const original = AntdConfig.settings.renderButton as ButtonFactory;
  const button = original({ ...props, ...(help ? { "aria-label": help.name } : {}) }, ctx);
  return help
    ? (createElement(Tooltip, { title: help.title, key: type }, button) as ReactElement)
    : button;
}) as ButtonFactory;

/**
 * Build the query-builder configuration from the catalogue the API published.
 *
 * Nothing here is hardcoded per dataset: adding a filterable column to an
 * endpoint makes it appear in the builder, with its operators, on the next
 * page load.
 */
export function queryBuilderConfig(fields: ExplorerField[]): Config {
  return {
    ...AntdConfig,
    types: builderTypes(),
    operators: builderOperatorDefinitions(),
    settings: {
      ...AntdConfig.settings,
      showNot: true,
      canReorder: true,
      canRegroup: true,
      // Matches MAX_DEPTH and MAX_RULES in core/rules.py, so the editor stops
      // at the limit rather than letting the server reject a finished query.
      maxNesting: 12,
      maxNumberOfRules: 200,
      renderSize: "small",
      // A rule half-typed is the normal state of an editor being used, and
      // `compile_tree` skips incomplete rules by design. Dropping them on load
      // makes "Add rule" appear to do nothing.
      removeEmptyRulesOnLoad: false,
      removeIncompleteRulesOnLoad: false,
      removeEmptyGroupsOnLoad: false,
      // The API compares a column against a value. It cannot compare two
      // columns, nor evaluate a function, so neither is offered: an operator
      // the builder shows is an operator the backend will honour.
      valueSourcesInfo: { value: { label: "Value" } },
      // Every control says what it does on hover. The library's own buttons
      // are icons with no accessible name and no title — "what does the
      // circle-plus next to the plus do" is a question the editor was
      // silently asking of everybody who opened it (§55, §76).
      renderButton: renderLabelledButton,
    },
    fields: Object.fromEntries(
      fields
        .filter((field) => field.filterable)
        .map((field) => [
          field.name,
          {
            label: field.label,
            type: BUILDER_TYPE[field.kind],
            operators: builderOperators(field),
            valueSources: ["value"],
            fieldSettings: fieldSettings(field),
          },
        ]),
    ),
  };
}
