"""Declarative search, filter, sort and facets for every list endpoint.

Every table in the UI is searchable, filterable and sortable on every column,
and all of it happens in PostgreSQL. A client that filters a page it already
downloaded is filtering 25 of 200,000 rows while presenting the answer as if it
covered all of them (§71).

Rather than hand-writing that per endpoint — which is how one table ends up
case-sensitive and another silently ignores `sort` — each endpoint declares its
columns once:

    FIELDS = FieldSet(
        Field("name", User.full_name, searchable=True),
        Field("status", User.status, kind="enum", facet=True),
        Field("created_at", User.created_at, kind="datetime"),
    )

Parameter shapes, by field kind:

    text      ?name=ana                contains, case-insensitive
              ?name=ana,ben            contains any of them
    enum      ?status=ACTIVE,SUSPENDED exact, any of them
    bool      ?is_admin=true
    number    ?score=5 · ?score_min=1 · ?score_max=9
    datetime  ?created_at_from=2026-01-01 · ?created_at_to=2026-01-31
    uuid      ?org_id=<uuid>,<uuid>
    json      ?metadata=needle         searches the rendered document

Any filter may carry an explicit operator with a `__` suffix, which is what
turns a filter box into a query language and is the same operator vocabulary
the advanced query builder compiles to (§4):

    ?name__eq=Ana Pop           exactly this, case-insensitively
    ?name__not=test             does NOT contain this
    ?title__starts=Q4           begins with
    ?score__between=10,90       inclusive range
    ?owner__empty=true          has no value at all
    ?status__in=NEW,ASSIGNED    one of

Plus `?q=` across every field marked `searchable`, and `?sort=&order=` over any
field marked `sortable`.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, String, and_, cast, func, or_, select

from client.errors import ValidationError

#: A filter value long enough to be a mistake or an attack, not a search term.
MAX_FILTER_CHARS = 500
#: Guards `IN (...)` against a client pasting a whole column into one parameter.
MAX_FILTER_VALUES = 200

KINDS = frozenset({"text", "enum", "bool", "number", "datetime", "uuid", "json", "array"})


@dataclass(frozen=True, slots=True)
class Field:
    """One column an endpoint exposes to filtering, sorting and search."""

    name: str
    column: Any
    kind: str = "text"
    sortable: bool = True
    filterable: bool = True
    #: Included in the free-text `q` sweep. Only ever text-shaped columns: a
    #: `q` that silently matches a UUID prefix looks broken to whoever typed it.
    searchable: bool = False
    #: Offer distinct values with counts so the filter menu is built from the
    #: data rather than a hardcoded list that drifts.
    facet: bool = False
    #: Human label the frontend query builder shows for this field.
    label: str = ""
    #: Fixed choice list for enum fields, so the builder can render a select
    #: without a round trip.
    choices: tuple[str, ...] = ()
    #: Extra names this column may be sorted by, for URLs already in the wild.
    #: Deliberately not filter parameters: two spellings of one filter is how a
    #: column ends up narrowed twice by contradictory clauses.
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in KINDS:  # pragma: no cover - programmer error
            raise ValueError(f"unknown field kind {self.kind!r}")

    @property
    def title(self) -> str:
        """The heading and query-builder label for this column.

        Sentence case, not Title Case: it is what the explicit labels in the
        resource declarations already use ("Due date", "SLA breached"), and a
        column list mixing "Battery Percent" with "Due date" reads as two
        products. An acronym or a unit still needs an explicit `label`.
        """
        if self.label:
            return self.label
        spaced = self.name.replace("_", " ")
        return spaced[:1].upper() + spaced[1:]

    @property
    def expression(self):
        """The comparable SQL expression. JSON/array columns are compared as
        their rendered text — cheap enough for a filter nobody runs in a loop,
        and the alternative is a generated column plus a migration per filter."""
        if self.kind in ("json", "array"):
            return cast(self.column, String)
        return self.column


@dataclass(frozen=True, slots=True)
class FieldSet:
    fields: tuple[Field, ...]
    by_name: dict[str, Field] = dataclass_field(default_factory=dict)

    def __init__(self, *fields: Field) -> None:
        object.__setattr__(self, "fields", tuple(fields))
        index: dict[str, Field] = {}
        for spec in fields:
            index[spec.name] = spec
            for alias in spec.aliases:
                index[alias] = spec
        object.__setattr__(self, "by_name", index)

    @property
    def searchable(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.searchable)

    @property
    def facets(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.facet)

    def sort_column(self, name: str, fallback: str):
        spec = self.by_name.get(name)
        if spec is None or not spec.sortable:
            spec = self.by_name[fallback]
        return spec.column

    def describe(self) -> list[dict[str, Any]]:
        """The field catalogue the advanced query builder is generated from
        (§4). Shipping it from the same declaration the SQL is built from is
        what stops the builder offering an operator the backend cannot honour."""
        return [
            {
                "name": f.name,
                "label": f.title,
                "kind": f.kind,
                "sortable": f.sortable,
                "filterable": f.filterable,
                "searchable": f.searchable,
                "facet": f.facet,
                "operators": sorted(OPERATORS_BY_KIND.get(f.kind, ())),
                "choices": list(f.choices),
            }
            for f in self.fields
        ]


# ── value coercion ───────────────────────────────────────────────────────


def _as_text(raw: Any) -> str:
    """One filter value as the comma-separated string every reader expects.

    Filters arrive from two places with two shapes: a query string, where
    `?status=A,B` is already text, and a JSON request body, where the same
    filter is `["A", "B"]`. Stringifying the list without this produces
    `"['A', 'B']"` and a WHERE clause that matches nothing at all — a filter
    that silently returns an empty table rather than failing.
    """
    if isinstance(raw, (list, tuple, set)):
        return ",".join(str(value) for value in raw)
    return str(raw)


def _values(raw: Any, *, name: str) -> list[str]:
    text = _as_text(raw)
    if len(text) > MAX_FILTER_CHARS:
        raise ValidationError(f"{name} filter must be at most {MAX_FILTER_CHARS} characters")
    values = [part.strip() for part in text.split(",") if part.strip()]
    if len(values) > MAX_FILTER_VALUES:
        raise ValidationError(f"{name} accepts at most {MAX_FILTER_VALUES} values")
    return values


def _number(raw: Any, *, name: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must be a number") from exc


def _moment(raw: Any, *, name: str) -> datetime:
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(f"{name} must be an ISO-8601 date or timestamp") from exc
    # A naive boundary from a date picker means "that instant in UTC"; leaving
    # it naive makes PostgreSQL compare it against a tz-aware column and fail.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _uuids(values: list[str], *, name: str) -> list[UUID]:
    try:
        return [UUID(str(value)) for value in values]
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} must contain only UUIDs") from exc


def _typed(spec: Field, values: list[str]):
    """Coerce raw strings to the column's Python type for exact comparison."""
    if spec.kind == "uuid":
        return _uuids(values, name=spec.name)
    if spec.kind == "number":
        return [_number(v, name=spec.name) for v in values]
    if spec.kind == "datetime":
        return [_moment(v, name=spec.name) for v in values]
    if spec.kind == "bool":
        return [str(v).lower() in ("true", "1", "yes") for v in values]
    return values


# ── operators ────────────────────────────────────────────────────────────

#: The full operator vocabulary of §4. `apply_filters` reads these off `__`
#: suffixes; `core/rules.py` compiles the query-builder tree into the same set,
#: so the simple filter bar and the advanced builder can never disagree about
#: what "starts with" means.
OPERATORS = frozenset(
    {
        "eq", "ne", "contains", "not", "starts", "ends",
        "gt", "gte", "lt", "lte", "between",
        "before", "after", "in", "not_in",
        "empty", "not_empty", "exists", "not_exists",
    }
)

_TEXTUAL = {"eq", "ne", "contains", "not", "starts", "ends", "in", "not_in", "empty", "not_empty", "exists", "not_exists"}
_ORDERED = {"eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in", "empty", "not_empty", "exists", "not_exists"}
_TEMPORAL = {"eq", "ne", "before", "after", "gt", "gte", "lt", "lte", "between", "empty", "not_empty", "exists", "not_exists"}
_EXACT = {"eq", "ne", "in", "not_in", "empty", "not_empty", "exists", "not_exists"}

OPERATORS_BY_KIND: dict[str, frozenset[str]] = {
    "text": frozenset(_TEXTUAL),
    "json": frozenset(_TEXTUAL),
    "array": frozenset(_TEXTUAL),
    "enum": frozenset(_EXACT),
    "uuid": frozenset(_EXACT),
    "bool": frozenset({"eq", "ne", "empty", "not_empty"}),
    "number": frozenset(_ORDERED),
    "datetime": frozenset(_TEMPORAL),
}

#: Wire spellings the frontend query builder may send, mapped to the canonical
#: name. Keeping the alias table here means a UI library's vocabulary never
#: leaks into the SQL layer.
OPERATOR_ALIASES = {
    "equal": "eq", "equals": "eq", "==": "eq", "=": "eq", "select_equals": "eq",
    "not_equal": "ne", "!=": "ne", "<>": "ne", "select_not_equals": "ne",
    "like": "contains", "not_like": "not", "does_not_contain": "not",
    "starts_with": "starts", "ends_with": "ends",
    "greater": "gt", ">": "gt", "greater_or_equal": "gte", ">=": "gte",
    "less": "lt", "<": "lt", "less_or_equal": "lte", "<=": "lte",
    "range": "between", "between_dates": "between",
    "date_before": "before", "date_after": "after",
    "select_any_in": "in", "multiselect_equals": "in", "any_in": "in",
    "select_not_any_in": "not_in", "multiselect_not_equals": "not_in", "not_any_in": "not_in",
    "is_empty": "empty", "is_null": "empty", "is_not_empty": "not_empty",
    "is_not_null": "not_empty", "is_true": "eq", "is_false": "ne",
}


def canonical_operator(raw: str) -> str:
    key = str(raw or "").strip().lower()
    key = OPERATOR_ALIASES.get(key, key)
    if key not in OPERATORS:
        raise ValidationError(
            f"{raw!r} is not a filter operator; use one of " + ", ".join(sorted(OPERATORS))
        )
    return key


#: How PostgreSQL renders an *empty* collection when a JSON or array column is
#: cast to text. An absence, not a value: "records with no tags" has to find
#: the record whose tags are `{}` as well as the one whose tags are NULL.
_EMPTY_RENDERINGS = ("{}", "[]", "null")


def _blank(column, kind: str):
    """"Empty" means empty *or* absent: a NULL description and an empty-string
    description are the same absence to whoever is asking.

    And an empty *collection* is the same absence again. `json` and `array`
    columns are compared as their rendered text, and an empty array renders as
    `{}` — two characters, so a length test alone called it a value and
    "records with no tags" quietly answered only the ones whose column was
    NULL. Found by the operator matrix in `tests/test_query.py`, which is the
    first thing to ask every operator about every kind.
    """
    if kind in ("json", "array"):
        rendered = func.trim(cast(column, String))
        return or_(
            column.is_(None),
            func.length(rendered) == 0,
            rendered.in_(_EMPTY_RENDERINGS),
        )
    if kind == "text":
        return or_(column.is_(None), func.length(func.trim(cast(column, String))) == 0)
    return column.is_(None)


def build_predicate(spec: Field, operator: str, raw: Any):
    """One field, one operator, one value → a SQLAlchemy predicate.

    Returns None when the clause would select every row, so a caller can skip
    it instead of appending `WHERE true`.
    """
    op = canonical_operator(operator)
    column = spec.expression
    allowed = OPERATORS_BY_KIND.get(spec.kind, OPERATORS)
    if op not in allowed:
        raise ValidationError(
            f"{op!r} cannot be applied to {spec.name!r} ({spec.kind}); "
            "use one of " + ", ".join(sorted(allowed))
        )

    # Presence operators ignore the value entirely.
    if op in ("empty", "not_exists"):
        return _blank(column, spec.kind)
    if op in ("not_empty", "exists"):
        return ~_blank(column, spec.kind)

    if isinstance(raw, (list, tuple)):
        values = [str(v).strip() for v in raw if str(v).strip() != ""]
    else:
        values = _values(str(raw), name=spec.name) if raw is not None else []
    if not values:
        return None

    if op == "between":
        if len(values) < 2:
            raise ValidationError(f"{spec.name} between needs two values")
        low, high = _typed(spec, values[:2])
        if low > high:
            low, high = high, low
        return and_(column >= low, column <= high)

    if op in ("gt", "gte", "lt", "lte", "before", "after"):
        bound = _typed(spec, values[:1])[0]
        return {
            "gt": column > bound,
            "after": column > bound,
            "gte": column >= bound,
            "lt": column < bound,
            "before": column < bound,
            "lte": column <= bound,
        }[op]

    if op == "eq":
        # Case-insensitive for text, because a filter box is not a database
        # console and nobody types a name with the right capitals.
        if spec.kind in ("text", "json", "array"):
            return or_(*(func.lower(column) == v.lower() for v in values))
        return column.in_(_typed(spec, values))

    if op == "ne":
        if spec.kind in ("text", "json", "array"):
            # A row with no value is not "equal to X", so it must survive a
            # "not equal to X" filter.
            return and_(*(or_(column.is_(None), func.lower(column) != v.lower()) for v in values))
        return or_(column.is_(None), column.notin_(_typed(spec, values)))

    if op == "in":
        if spec.kind in ("text", "json", "array"):
            return or_(*(func.lower(column) == v.lower() for v in values))
        return column.in_(_typed(spec, values))

    if op == "not_in":
        if spec.kind in ("text", "json", "array"):
            return and_(*(or_(column.is_(None), func.lower(column) != v.lower()) for v in values))
        return or_(column.is_(None), column.notin_(_typed(spec, values)))

    if op == "not":
        # Excluding a value must not also exclude every row that has none: a
        # task with no description is not "a task containing 'urgent'".
        return and_(*(or_(column.is_(None), ~column.ilike(f"%{v}%")) for v in values))

    if op == "starts":
        return or_(*(column.ilike(f"{v}%") for v in values))

    if op == "ends":
        return or_(*(column.ilike(f"%{v}") for v in values))

    # contains
    return or_(*(column.ilike(f"%{v}%") for v in values))


def _default_predicate(spec: Field, raw: Any):
    """The clause a bare `?field=value` means, per kind."""
    values = _values(raw, name=spec.name)
    if not values:
        return None
    column = spec.expression

    if spec.kind == "bool":
        lowered = values[0].lower()
        if lowered not in ("true", "false"):
            raise ValidationError(f"{spec.name} must be true or false")
        return column.is_(lowered == "true")

    if spec.kind in ("enum", "uuid", "number"):
        return column.in_(_typed(spec, values))

    if spec.kind == "datetime":
        # A bare datetime filter is a same-day match; ranges use _from/_to.
        moment = _moment(values[0], name=spec.name)
        return func.date_trunc("day", column) == func.date_trunc("day", moment)

    return or_(*(column.ilike(f"%{v}%") for v in values))


# ── statement builders ───────────────────────────────────────────────────


def _blank_argument(raw: Any) -> bool:
    """No value at all — as a missing key, an empty string or an empty list.

    A cleared multi-select sends `[]`, which means "do not narrow by this",
    not "narrow by nothing".
    """
    if raw is None:
        return True
    if isinstance(raw, (list, tuple, set)):
        return not any(str(value).strip() for value in raw)
    return not str(raw).strip()


def apply_filters(stmt: Select, args, spec: FieldSet) -> Select:
    """Narrow `stmt` by every recognised query parameter in `args`."""
    for field_spec in spec.fields:
        if not field_spec.filterable:
            continue
        name = field_spec.name
        raw = args.get(name)
        if not _blank_argument(raw):
            predicate = _default_predicate(field_spec, raw)
            if predicate is not None:
                stmt = stmt.where(predicate)

        if field_spec.kind in ("number", "datetime"):
            convert = _number if field_spec.kind == "number" else _moment
            low = args.get(f"{name}_min") or args.get(f"{name}_from")
            high = args.get(f"{name}_max") or args.get(f"{name}_to")
            if low:
                stmt = stmt.where(field_spec.column >= convert(_as_text(low), name=name))
            if high:
                stmt = stmt.where(field_spec.column <= convert(_as_text(high), name=name))

    # Explicit operators, e.g. `?title__not=draft`. Applied after the plain
    # filters so one field can carry both: "contains X but not Y" is among the
    # most common things anybody wants to ask.
    for key in list(args.keys()):
        if "__" not in str(key):
            continue
        name, _, operator = str(key).rpartition("__")
        field_spec = spec.by_name.get(name)
        if field_spec is None or not field_spec.filterable:
            continue
        raw = args.get(key)
        if _blank_argument(raw):
            continue
        predicate = build_predicate(field_spec, operator, raw)
        if predicate is not None:
            stmt = stmt.where(predicate)

    term = _as_text(args.get("q") or "").strip()
    if term:
        if len(term) > MAX_FILTER_CHARS:
            raise ValidationError(f"q must be at most {MAX_FILTER_CHARS} characters")
        searchable = spec.searchable
        if searchable:
            stmt = stmt.where(or_(*(f.expression.ilike(f"%{term}%") for f in searchable)))
    return stmt


def apply_sort(stmt: Select, page, spec: FieldSet, *, default: str) -> Select:
    """Order by the requested column, keeping NULLs out of the reader's way.

    Descending means "most interesting first", and a NULL is never the most
    interesting row — an undated record at the top of a newest-first list is
    exactly where nobody expects it.

    Multi-column sort (§3) rides in as `sort=a,b` / `order=asc,desc`; the extra
    keys are applied in order after the primary one.
    """
    fields = [f.strip() for f in str(page.sort or "").split(",") if f.strip()] or [default]
    orders = [o.strip() for o in str(page.order or "desc").split(",") if o.strip()]

    clauses = []
    for index, name in enumerate(fields):
        column = spec.sort_column(name, default)
        direction = orders[index] if index < len(orders) else orders[-1] if orders else "desc"
        clauses.append(
            column.desc().nullslast() if direction == "desc" else column.asc().nullsfirst()
        )

    # A total order, always. Two rows sharing an `updated_at` have no defined
    # position relative to each other, and PostgreSQL is free to return them in
    # a different order for each query — so page 2 of an OFFSET scan can repeat
    # a row from page 1 and never show another one at all. A seeded dataset,
    # where thousands of rows are written in one transaction, hits this
    # immediately; production hits it eventually and blames the reader.
    identity = spec.by_name.get("id")
    if identity is not None and "id" not in fields:
        clauses.append(identity.column.asc())
    return stmt.order_by(*clauses)


def count_of(session, stmt: Select) -> int:
    """Total matching rows, without the LIMIT/OFFSET of the page itself.

    The limit is *stripped* rather than assumed absent. Every caller today
    counts before paging, so the promise held by convention — and a promise
    held by convention is one the next caller breaks, in the quietest way
    available: a footer reading "1–25 of 25" for a filtered set of four
    thousand.
    """
    return session.scalar(
        select(func.count()).select_from(stmt.limit(None).offset(None).subquery())
    ) or 0


def facets_for(session, stmt: Select, spec: FieldSet, *, limit: int = 50) -> dict[str, list[dict]]:
    """Distinct values and counts for each faceted column, under the *other*
    filters currently applied.

    Computed from the filtered statement so the menu shows what is reachable
    from where the user already is, rather than every value in the table. The
    statement is reused rather than rebuilt, which is what keeps facet counts
    honest: they can never disagree with the rows below them.
    """
    out: dict[str, list[dict]] = {}
    for field_spec in spec.facets:
        column = field_spec.column
        counted = (
            stmt.with_only_columns(column, func.count(), maintain_column_froms=True)
            .group_by(column)
            .order_by(func.count().desc())
            .limit(limit)
        )
        out[field_spec.name] = [
            {"value": str(value), "count": count}
            for value, count in session.execute(counted).all()
            if value is not None
        ]
    return out
