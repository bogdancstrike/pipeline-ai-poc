"""
`client.rules` — the advanced builder's tree, compiled and described.

Two outputs from one tree, and they must never disagree: the SQL the search
runs, and the sentence the inspector shows above it. A reader who is told
"Sentiment is NEGATIVE AND (Persons > 0)" and gets rows that do not match has
no way to tell which half lied.
"""

import pytest
from sqlalchemy import select

from client.errors import ValidationError
from client.models import VideoRecord
from client.resources import FIELDS
from client.rules import MAX_DEPTH, compile_tree, describe_tree, rule_count


def rule(field, operator, value, node_id="r1"):
    return {
        "id": node_id,
        "type": "rule",
        "properties": {"field": field, "operator": operator, "value": value},
    }


def group(*children, conjunction="AND", negated=False):
    return {
        "id": "g1",
        "type": "group",
        "properties": {"conjunction": conjunction, "not": negated},
        "children1": {child.get("id", str(index)): child for index, child in enumerate(children)},
    }


def sql(tree) -> str:
    predicate = compile_tree(tree, FIELDS)
    if predicate is None:
        return ""
    statement = select(VideoRecord).where(predicate)
    return str(statement.compile(compile_kwargs={"literal_binds": True})).partition("WHERE")[2]


# ── an empty or unfinished tree narrows nothing ──────────────────────────


@pytest.mark.parametrize("nothing", [None, {}, {"type": "group", "children1": {}}])
def test_an_empty_tree_compiles_to_no_narrowing(nothing):
    """Not to "match nothing": the table must not blank while a rule is typed."""
    assert compile_tree(nothing, FIELDS) is None


def test_a_rule_with_no_value_yet_is_skipped_not_rejected():
    tree = group(rule("sentiment", "select_equals", []))
    assert compile_tree(tree, FIELDS) is None


def test_a_finished_rule_beside_an_unfinished_one_still_narrows():
    tree = group(
        rule("sentiment", "select_equals", ["NEGATIVE"], node_id="a"),
        rule("name", "like", "", node_id="b"),
    )
    rendered = sql(tree)
    assert "sentiment" in rendered
    assert "name" not in rendered


def test_a_rule_with_no_field_is_skipped():
    assert compile_tree(group(rule("", "eq", "x")), FIELDS) is None


# ── conjunctions, negation and nesting ───────────────────────────────────


def test_and_joins_every_child():
    tree = group(
        rule("sentiment", "select_equals", ["NEGATIVE"], node_id="a"),
        rule("person_count", "greater", 0, node_id="b"),
    )
    rendered = sql(tree).upper()
    assert " AND " in rendered
    assert "SENTIMENT" in rendered and "PERSON_COUNT" in rendered


def test_or_widens_instead():
    tree = group(
        rule("sentiment", "select_equals", ["NEGATIVE"], node_id="a"),
        rule("sentiment", "select_equals", ["POSITIVE"], node_id="b"),
        conjunction="OR",
    )
    assert " OR " in sql(tree).upper()


def test_not_inverts_the_whole_group():
    tree = group(rule("sentiment", "select_equals", ["NEGATIVE"]), negated=True)
    assert "NOT" in sql(tree).upper()


def test_a_nested_group_keeps_its_own_brackets():
    """`A and (B or C)` must not compile to `(A and B) or C`."""
    inner = {
        "id": "g2",
        "type": "group",
        "properties": {"conjunction": "OR"},
        "children1": {
            "c1": rule("sentiment", "select_equals", ["NEGATIVE"], node_id="c1"),
            "c2": rule("sentiment", "select_equals", ["POSITIVE"], node_id="c2"),
        },
    }
    tree = group(rule("person_count", "greater", 0, node_id="a"), inner)

    rendered = sql(tree).upper()
    assert " OR " in rendered and " AND " in rendered
    # The OR has to be bracketed, or the AND would bind tighter than intended.
    assert "(" in rendered


def test_a_conjunction_that_is_not_and_or_or_is_refused():
    with pytest.raises(ValidationError):
        compile_tree(group(rule("name", "like", "x"), conjunction="XOR"), FIELDS)


def test_a_tree_nested_past_the_limit_is_refused():
    """A runaway tree is a stack overflow and a query planner's bad day."""
    node = rule("name", "like", "x")
    for depth in range(MAX_DEPTH + 2):
        node = {
            "id": f"g{depth}",
            "type": "group",
            "properties": {"conjunction": "AND"},
            "children1": {"c": node},
        }
    with pytest.raises(ValidationError) as caught:
        compile_tree(node, FIELDS)
    assert "nest" in str(caught.value).lower()


def test_children_may_arrive_as_a_list_as_well_as_a_map():
    """Saved trees predate the library's current export shape."""
    tree = {
        "type": "group",
        "conjunction": "AND",
        "children1": [rule("sentiment", "select_equals", ["NEGATIVE"])],
    }
    assert "sentiment" in sql(tree)


def test_group_settings_may_be_top_level_or_under_properties():
    top_level = {
        "type": "group",
        "conjunction": "OR",
        "children1": {
            "a": rule("sentiment", "select_equals", ["NEGATIVE"], node_id="a"),
            "b": rule("sentiment", "select_equals", ["POSITIVE"], node_id="b"),
        },
    }
    assert " OR " in sql(top_level).upper()


# ── refusals that protect the SQL layer ──────────────────────────────────


def test_an_unknown_field_is_refused_and_lists_the_ones_that_exist():
    with pytest.raises(ValidationError) as caught:
        compile_tree(group(rule("salary", "equal", "x")), FIELDS)
    message = str(caught.value)
    assert "salary" in message


def test_an_unknown_node_type_is_refused():
    with pytest.raises(ValidationError):
        compile_tree({"type": "spreadsheet", "children1": {}}, FIELDS)


def test_an_operator_the_field_cannot_honour_is_refused():
    with pytest.raises(ValidationError):
        compile_tree(group(rule("sentiment", "like", "NEG")), FIELDS)


# ── the sentence shown above the results ─────────────────────────────────


def test_the_description_uses_the_fields_human_label():
    tree = group(rule("person_count", "greater", 0))
    assert "Persons" in describe_tree(tree, FIELDS)


def test_the_description_names_the_conjunction_between_rules():
    tree = group(
        rule("sentiment", "select_equals", ["NEGATIVE"], node_id="a"),
        rule("person_count", "greater", 0, node_id="b"),
        conjunction="OR",
    )
    assert "OR" in describe_tree(tree, FIELDS)


def test_the_root_group_is_not_wrapped_in_pointless_brackets():
    tree = group(rule("sentiment", "select_equals", ["NEGATIVE"]))
    assert not describe_tree(tree, FIELDS).strip().startswith("(")


def test_a_negated_group_says_not():
    tree = group(rule("sentiment", "select_equals", ["NEGATIVE"]), negated=True)
    assert describe_tree(tree, FIELDS).strip().startswith("NOT")


def test_an_unfinished_rule_is_absent_from_the_description_too():
    """The sentence and the SQL skip the same rules, or one of them is lying."""
    tree = group(
        rule("sentiment", "select_equals", ["NEGATIVE"], node_id="a"),
        rule("name", "like", "", node_id="b"),
    )
    described = describe_tree(tree, FIELDS)
    assert "Sentiment" in described
    assert "Video" not in described


def test_a_between_rule_reads_as_a_range():
    tree = group(rule("person_count", "range", [1, 3]))
    described = describe_tree(tree, FIELDS)
    assert "1" in described and "3" in described
    assert "AND" in described


def test_an_empty_tree_describes_as_nothing():
    assert describe_tree(None, FIELDS) == ""
    assert describe_tree({}, FIELDS) == ""


# ── how many rules a saved search carries ────────────────────────────────


def test_rule_count_counts_leaves_at_every_depth():
    inner = {
        "type": "group",
        "properties": {"conjunction": "OR"},
        "children1": {
            "c1": rule("sentiment", "select_equals", ["NEGATIVE"], node_id="c1"),
            "c2": rule("sentiment", "select_equals", ["POSITIVE"], node_id="c2"),
        },
    }
    tree = group(rule("person_count", "greater", 0, node_id="a"), inner)
    assert rule_count(tree) == 3


@pytest.mark.parametrize("nothing", [None, {}, []])
def test_rule_count_of_nothing_is_zero(nothing):
    assert rule_count(nothing) == 0
