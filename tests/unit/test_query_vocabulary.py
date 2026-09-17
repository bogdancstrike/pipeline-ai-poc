"""
`client.query` — the filter vocabulary the whole app shares.

The filter bar, the advanced builder and the export all compile into these
operators, so a disagreement here is a disagreement between two screens about
what "starts with" means. The SQL is rendered rather than executed: what is
being pinned is the translation, and it needs no database to be wrong.
"""

import pytest
from sqlalchemy import select

from client.errors import ValidationError
from client.models import VideoRecord
from client.pagination import Page
from client.query import (
    MAX_FILTER_CHARS,
    MAX_FILTER_VALUES,
    OPERATORS,
    OPERATORS_BY_KIND,
    apply_filters,
    apply_sort,
    canonical_operator,
)
from client.resources import FIELDS


def sql_for(**filters) -> str:
    """The WHERE clause a filter argument compiles to, as text.

    Only the clause: the SELECT list names every column of the table and would
    otherwise answer "is this column filtered on?" with a yes for all of them.
    """
    statement = apply_filters(select(VideoRecord), filters, FIELDS)
    rendered = str(statement.compile(compile_kwargs={"literal_binds": True}))
    return rendered.partition("WHERE")[2] or rendered


def sorted_by(field: str, order: str = "desc") -> str:
    page = Page(page=1, page_size=25, sort=field, order=order)
    return str(apply_sort(select(VideoRecord), page, FIELDS, default="analysed_at"))


# ── the operator table ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("wire", "canonical"),
    [
        ("equal", "eq"), ("equals", "eq"), ("==", "eq"), ("select_equals", "eq"),
        ("not_equal", "ne"), ("!=", "ne"), ("select_not_equals", "ne"),
        ("like", "contains"), ("not_like", "not"), ("does_not_contain", "not"),
        ("starts_with", "starts"), ("ends_with", "ends"),
        ("greater", "gt"), ("greater_or_equal", "gte"),
        ("less", "lt"), ("less_or_equal", "lte"),
        ("range", "between"), ("between_dates", "between"),
        ("date_before", "before"), ("date_after", "after"),
        ("select_any_in", "in"), ("multiselect_equals", "in"),
        ("select_not_any_in", "not_in"),
        ("is_empty", "empty"), ("is_null", "empty"),
        ("is_not_empty", "not_empty"), ("is_not_null", "not_empty"),
    ],
)
def test_the_query_builders_spelling_maps_to_one_canonical_operator(wire, canonical):
    """The UI library's vocabulary must never leak into the SQL layer."""
    assert canonical_operator(wire) == canonical


def test_an_operator_is_matched_whatever_its_case():
    assert canonical_operator("STARTS_WITH") == "starts"
    assert canonical_operator("  Equals  ") == "eq"


def test_an_unknown_operator_names_the_ones_that_exist():
    with pytest.raises(ValidationError) as caught:
        canonical_operator("sounds_like")
    assert "contains" in str(caught.value)


def test_every_canonical_operator_is_offered_to_at_least_one_kind():
    offered = set().union(*OPERATORS_BY_KIND.values())
    assert OPERATORS - offered == set()


@pytest.mark.parametrize(
    ("kind", "operator", "allowed"),
    [
        ("text", "contains", True),
        ("text", "gt", False),          # "greater than" over prose is nonsense
        ("enum", "eq", True),
        ("enum", "contains", False),    # a select cannot be substring-matched
        ("number", "between", True),
        ("number", "starts", False),
        ("datetime", "before", True),
        ("datetime", "contains", False),
        ("bool", "eq", True),
        ("bool", "gt", False),
    ],
)
def test_each_kind_only_offers_operators_it_can_honour(kind, operator, allowed):
    assert (operator in OPERATORS_BY_KIND[kind]) is allowed


# ── what a filter compiles to ────────────────────────────────────────────


def test_a_bare_filter_is_an_equality():
    assert "sentiment" in sql_for(sentiment="NEGATIVE")
    assert "NEGATIVE" in sql_for(sentiment="NEGATIVE")


def test_text_equality_is_case_insensitive():
    """`?name__eq=Ana` has to find `ana` — a filter box is not a shell."""
    assert "lower" in sql_for(name__eq="Ana").lower()


def test_contains_becomes_a_like_with_wildcards_on_both_sides():
    rendered = sql_for(summary__contains="ceuta").lower()
    assert "like" in rendered
    assert "%ceuta%" in rendered


def test_starts_anchors_the_wildcard_on_the_right_only():
    rendered = sql_for(name__starts="qa-").lower()
    assert "'qa-%'" in rendered


def test_ends_anchors_the_wildcard_on_the_left_only():
    rendered = sql_for(name__ends=".mp4").lower()
    assert "'%.mp4'" in rendered


def test_not_is_a_negated_like():
    rendered = sql_for(summary__not="ceuta").lower()
    assert "not" in rendered and "like" in rendered


def test_in_becomes_one_clause_not_a_string_comparison():
    rendered = sql_for(sentiment__in="NEGATIVE,POSITIVE").lower()
    assert "in (" in rendered
    assert "negative" in rendered and "positive" in rendered


def test_between_is_inclusive_on_both_ends():
    rendered = sql_for(person_count__between="1,3").lower()
    assert "between" in rendered or (">=" in rendered and "<=" in rendered)


@pytest.mark.parametrize("operator", ["gt", "gte", "lt", "lte"])
def test_the_ordered_operators_compile_over_a_number(operator):
    rendered = sql_for(**{f"person_count__{operator}": "2"})
    assert "person_count" in rendered


def test_empty_finds_the_absent_as_well_as_the_blank():
    """"No summary" has to mean NULL *and* the empty string, or it lies."""
    rendered = sql_for(summary__empty="true").lower()
    assert "is null" in rendered


def test_not_empty_is_the_complement_of_empty():
    rendered = sql_for(summary__not_empty="true").lower()
    assert "is not null" in rendered or "not" in rendered


def test_a_json_column_is_compared_as_text():
    """`persons` is JSONB; filtering it casts rather than needing a migration."""
    rendered = sql_for(persons__contains="222").lower()
    assert "cast" in rendered or "::" in rendered


@pytest.mark.parametrize("word", ["true", "True", "TRUE"])
def test_a_bare_boolean_filter_takes_the_word_in_any_case(word):
    assert "is true" in sql_for(mocked=word).lower()


def test_a_bare_boolean_filter_refuses_anything_but_true_or_false():
    """`?mocked=1` is a 400, while `?mocked__eq=1` is accepted.

    The two paths coerce differently — the bare filter demands the word, the
    explicit operator runs the value through `_typed`, which also takes 1/yes/on.
    Pinned rather than corrected: the frontend only ever sends the words, and a
    filter that refuses what it cannot interpret is the safer of the two.
    """
    with pytest.raises(ValidationError):
        sql_for(mocked="1")

    assert "in (true)" in sql_for(mocked__eq="1").lower()


# ── the free-text sweep ──────────────────────────────────────────────────


def test_q_sweeps_every_searchable_field_and_nothing_else():
    rendered = sql_for(q="ceuta").lower()

    for searchable in ("summary", "transcript", "description", "ocr_text", "entities_text"):
        assert searchable in rendered
    # prompt_hash is not marked searchable: a `q` that matches a hash prefix
    # looks broken to whoever typed a word.
    assert "prompt_hash" not in rendered


def test_q_is_one_or_over_the_columns_not_an_and():
    assert " or " in sql_for(q="ceuta").lower()


# ── refusals ─────────────────────────────────────────────────────────────


def test_an_undeclared_parameter_is_ignored_rather_than_refused():
    """A filter nobody declared narrows nothing, and does not fail the request.

    Deliberate: the same argument bag carries `page`, `sort` and whatever else
    a URL accumulated, and refusing an unrecognised key would make a pasted
    link a 400. The cost is that a *misspelt* filter silently returns the
    unfiltered table, which is why the field catalogue is published and the
    frontend builds its controls from it rather than from hardcoded names.
    """
    assert sql_for(no_such_column="x") == sql_for()


def test_a_field_that_is_not_sortable_falls_back_to_the_default():
    """`search_text` is five columns concatenated — ordering by it is meaningless.

    The fallback is deliberate rather than an error: a sort parameter is a
    presentation detail, and refusing the whole page over one is worse than
    showing it in the default order.
    """
    rendered = sorted_by("search_text")
    assert "analysed_at" in rendered
    assert "search_text" not in rendered.split("ORDER BY")[-1]


def test_an_overlong_filter_value_is_refused():
    with pytest.raises(ValidationError):
        sql_for(name="x" * (MAX_FILTER_CHARS + 1))


def test_too_many_values_in_one_in_clause_are_refused():
    with pytest.raises(ValidationError):
        sql_for(sentiment__in=",".join(str(n) for n in range(MAX_FILTER_VALUES + 1)))


def test_a_filter_value_with_a_quote_is_bound_not_interpolated():
    """The defence against injection is binding, and it has to stay that way."""
    statement = apply_filters(
        select(VideoRecord), {"name": "x'; DROP TABLE video_records;--"}, FIELDS
    )
    # Without literal_binds the value is a parameter, not part of the text.
    assert "DROP TABLE" not in str(statement)


# ── sorting ──────────────────────────────────────────────────────────────


def test_sorting_is_by_a_declared_field_in_a_declared_direction():
    assert "ORDER BY" in sorted_by("analysed_at", "desc")
    assert "DESC" in sorted_by("analysed_at", "desc")
    assert "ASC" in sorted_by("analysed_at", "asc")


def test_an_unknown_sort_field_cannot_reach_the_order_by():
    """A sort parameter is never interpolated: an unknown name is the default."""
    rendered = sorted_by("; DROP TABLE video_records; --")
    assert "DROP TABLE" not in rendered
    assert "analysed_at" in rendered


# ── the catalogue the frontend builds itself from ────────────────────────


def test_describe_publishes_every_field_with_its_operators():
    described = {entry["name"]: entry for entry in FIELDS.describe()}

    assert "sentiment" in described
    assert described["sentiment"]["kind"] == "enum"
    assert "NEGATIVE" in described["sentiment"]["choices"]
    assert "eq" in described["sentiment"]["operators"]
    # An enum must not be offered substring matching it cannot honour.
    assert "contains" not in described["sentiment"]["operators"]


def test_every_described_field_carries_a_human_label():
    for entry in FIELDS.describe():
        assert entry["label"], entry["name"]
        assert entry["label"][0] == entry["label"][0].upper()
