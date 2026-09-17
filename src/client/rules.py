"""Query-builder trees → SQL, and → readable text.

The advanced search screen (§4) and the alert-rule editor (§49) both build a
nested condition tree in the browser with react-awesome-query-builder. This
module is the one place that tree turns into anything else:

  * `compile_tree`  → a SQLAlchemy predicate, so nested AND/OR groups execute
                      in PostgreSQL like every other filter (§71);
  * `describe_tree` → the parenthesised text the query inspector shows (§51).

Both walk the same structure, so the text a user reads is provably the shape of
the SQL that ran — the entire point of an inspector is that it cannot drift
from what was executed.

Accepted shape (react-awesome-query-builder's native tree):

    {"type": "group", "conjunction": "AND", "not": false, "children1": {
        "a1": {"type": "rule", "properties": {
            "field": "status", "operator": "select_equals", "value": ["ACTIVE"]}},
        "a2": {"type": "group", "conjunction": "OR", "children1": [...]}}}

`children1` and `children` are both honoured, as dict (id → node) or list,
because the library emits both depending on export helper.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, false, not_, or_, true

from client.errors import ValidationError
from client.query import FieldSet, build_predicate, canonical_operator

#: A tree deep enough to be a denial-of-service rather than a question.
MAX_DEPTH = 12
MAX_RULES = 200

_TEXT_OPERATOR = {
    "eq": "=",
    "ne": "≠",
    "contains": "contains",
    "not": "does not contain",
    "starts": "starts with",
    "ends": "ends with",
    "gt": ">",
    "gte": "≥",
    "lt": "<",
    "lte": "≤",
    "between": "between",
    "before": "before",
    "after": "after",
    "in": "in",
    "not_in": "not in",
    "empty": "is empty",
    "not_empty": "is not empty",
    "exists": "exists",
    "not_exists": "does not exist",
}

_VALUELESS = {"empty", "not_empty", "exists", "not_exists"}


def _children(node: dict[str, Any]) -> list[dict[str, Any]]:
    raw = node.get("children1", node.get("children"))
    if raw is None:
        return []
    if isinstance(raw, dict):
        # Dict order is insertion order in Python 3.7+, and the library builds
        # it in on-screen order, so the inspector text matches the UI top-down.
        return [child for child in raw.values() if isinstance(child, dict)]
    if isinstance(raw, list):
        return [child for child in raw if isinstance(child, dict)]
    raise ValidationError("query group children must be a list or an object")


def _rule_parts(node: dict[str, Any]) -> tuple[str, str, Any]:
    """Field, operator and value of one rule; the field is "" when unchosen.

    A rule whose field has not been picked yet is the first state every rule
    passes through — the editor sends the tree on each change, and the drawer
    is open while it happens. Reporting that as an error would make adding a
    rule fail the request that is showing the results behind it, so it is
    reported as incomplete and skipped, exactly like a rule with no value.
    """
    props = node.get("properties") or {}
    field = props.get("field") or props.get("fieldName") or ""
    operator = props.get("operator") or "eq"
    value = props.get("value")
    if isinstance(value, list):
        # RAQB always wraps values in a list, one entry per operator cardinality
        # (two for `between`). A single-entry list is a scalar to us.
        flat = [v for v in value if v is not None and v != ""]
        if not flat:
            value = None
        elif len(flat) == 1 and canonical_operator(operator) != "between":
            value = flat[0]
        else:
            value = flat
    return str(field), str(operator), value


class _Counter:
    __slots__ = ("rules",)

    def __init__(self) -> None:
        self.rules = 0

    def tick(self) -> None:
        self.rules += 1
        if self.rules > MAX_RULES:
            raise ValidationError(f"a query may contain at most {MAX_RULES} rules")


def compile_tree(tree: dict[str, Any] | None, spec: FieldSet):
    """Compile a builder tree into one SQLAlchemy predicate.

    Returns None for an empty or all-incomplete tree, which callers read as
    "no additional narrowing" rather than "match nothing" — a half-built rule
    in the editor must not blank the results the user is looking at.
    """
    if not tree or not isinstance(tree, dict):
        return None
    return _compile_node(tree, spec, depth=0, counter=_Counter())


def _compile_node(node: dict[str, Any], spec: FieldSet, *, depth: int, counter: _Counter):
    if depth > MAX_DEPTH:
        raise ValidationError(f"query groups may nest at most {MAX_DEPTH} deep")

    kind = (node.get("type") or "group").lower()

    if kind in ("group", "rule_group"):
        properties = node.get("properties") or {}
        # RAQB's current export nests group settings under `properties`; older
        # saved trees and the deterministic seed use top-level keys. Supporting
        # both keeps persisted searches stable across library upgrades.
        conjunction = str(properties.get("conjunction") or node.get("conjunction") or "AND").upper()
        if conjunction not in ("AND", "OR"):
            raise ValidationError("conjunction must be AND or OR")
        parts = [
            compiled
            for child in _children(node)
            if (compiled := _compile_node(child, spec, depth=depth + 1, counter=counter))
            is not None
        ]
        if not parts:
            return None
        combined = and_(*parts) if conjunction == "AND" else or_(*parts)
        return not_(combined) if properties.get("not", node.get("not")) else combined

    if kind in ("rule", "field"):
        counter.tick()
        field, operator, value = _rule_parts(node)
        if not field:
            return None
        field_spec = spec.by_name.get(field)
        if field_spec is None:
            raise ValidationError(
                f"{field!r} is not a searchable field",
                details={"field": field, "available": sorted(spec.by_name)},
            )
        if not field_spec.filterable:
            raise ValidationError(f"{field!r} cannot be filtered")
        canonical = canonical_operator(operator)
        if value in (None, "", []) and canonical not in _VALUELESS:
            # An unfinished rule. Skipping it beats erroring: the editor sends
            # the tree on every keystroke and a half-typed rule is normal.
            return None
        return build_predicate(field_spec, canonical, value)

    raise ValidationError(f"unknown query node type {kind!r}")


def describe_tree(tree: dict[str, Any] | None, spec: FieldSet, *, indent: int = 0) -> str:
    """The parenthesised, indented rendering the query inspector shows (§51)."""
    if not tree or not isinstance(tree, dict):
        return ""
    return _describe_node(tree, spec, indent=indent, depth=0)


def _describe_node(node: dict[str, Any], spec: FieldSet, *, indent: int, depth: int) -> str:
    pad = "    " * indent
    kind = (node.get("type") or "group").lower()

    if kind in ("group", "rule_group"):
        if depth > MAX_DEPTH:
            return f"{pad}…"
        properties = node.get("properties") or {}
        conjunction = str(properties.get("conjunction") or node.get("conjunction") or "AND").upper()
        parts = [
            text
            for child in _children(node)
            if (text := _describe_node(child, spec, indent=indent + 1, depth=depth + 1)).strip()
        ]
        if not parts:
            return ""
        joiner = f"\n{pad}    {conjunction}\n"
        body = joiner.join(parts)
        negation = "NOT " if properties.get("not", node.get("not")) else ""
        if depth == 0 and not negation:
            # The root group needs no parentheses; they only add noise.
            return body
        return f"{pad}{negation}(\n{body}\n{pad})"

    field, operator, value = _rule_parts(node)
    if not field:
        return ""
    field_spec = spec.by_name.get(field)
    label = field_spec.title if field_spec else field
    try:
        canonical = canonical_operator(operator)
    except ValidationError:
        canonical = "eq"
    symbol = _TEXT_OPERATOR.get(canonical, canonical)

    if canonical in _VALUELESS:
        return f"{pad}{label} {symbol}"
    if value in (None, "", []):
        return ""
    if isinstance(value, (list, tuple)):
        if canonical == "between" and len(value) >= 2:
            rendered = f"{_literal(value[0])} AND {_literal(value[1])}"
        else:
            rendered = "[" + ", ".join(_literal(v) for v in value) + "]"
    else:
        rendered = _literal(value)
    return f"{pad}{label} {symbol} {rendered}"


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return text if text.replace(".", "", 1).isdigit() else f"'{text}'"


def rule_count(tree: dict[str, Any] | None) -> int:
    """How many complete rules a tree carries — shown on saved-search cards."""
    if not tree or not isinstance(tree, dict):
        return 0
    kind = (tree.get("type") or "group").lower()
    if kind in ("rule", "field"):
        return 1
    return sum(rule_count(child) for child in _children(tree))


def always(match: bool):
    """Explicit all/nothing predicates, so callers never pass a bare Python
    bool into `.where()` (SQLAlchemy 2 rejects it)."""
    return true() if match else false()
