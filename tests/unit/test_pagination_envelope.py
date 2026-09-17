"""
`client.pagination` — "page 7 of 42", and the refusals that keep it honest.

A page size is the one client-supplied number that decides how much work the
database does, so the ceiling is a guard rather than a preference.
"""

import pytest

from client.errors import ValidationError
from client.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PAGE_SIZE_CHOICES,
    Page,
    envelope,
    parse_page,
    parse_uuid,
)


# ── reading the request ──────────────────────────────────────────────────


def test_no_arguments_means_the_first_page_at_the_default_size():
    page = parse_page({}, default_sort="analysed_at")
    assert (page.page, page.page_size) == (1, DEFAULT_PAGE_SIZE)


def test_the_offset_follows_from_the_page_and_the_size():
    assert parse_page({"page": 3, "page_size": 25}, default_sort="x").offset == 50


def test_the_first_page_starts_at_zero():
    assert parse_page({"page": 1}, default_sort="x").offset == 0


def test_a_page_below_one_is_clamped_rather_than_refused():
    """`?page=0` is a link somebody built, not an attack."""
    assert parse_page({"page": 0}, default_sort="x").page == 1
    assert parse_page({"page": -5}, default_sort="x").page == 1


def test_the_sort_falls_back_to_the_endpoints_default():
    assert parse_page({}, default_sort="analysed_at").sort == "analysed_at"


def test_the_order_falls_back_to_newest_first():
    assert parse_page({}, default_sort="x").order == "desc"


def test_the_order_is_read_whatever_its_case():
    assert parse_page({"order": "ASC"}, default_sort="x").order == "asc"


# ── refusals ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["many", "1.5", None, [], {}])
def test_a_page_that_is_not_a_number_is_refused(bad):
    with pytest.raises(ValidationError):
        parse_page({"page": bad}, default_sort="x")


@pytest.mark.parametrize("bad", [0, -1, MAX_PAGE_SIZE + 1, 100_000])
def test_a_page_size_outside_the_ceiling_is_refused(bad):
    with pytest.raises(ValidationError) as caught:
        parse_page({"page_size": bad}, default_sort="x")
    assert str(MAX_PAGE_SIZE) in str(caught.value)


def test_the_largest_allowed_page_size_is_allowed():
    assert parse_page({"page_size": MAX_PAGE_SIZE}, default_sort="x").page_size == MAX_PAGE_SIZE


def test_an_order_that_is_neither_direction_is_refused():
    with pytest.raises(ValidationError):
        parse_page({"order": "sideways"}, default_sort="x")


def test_every_offered_page_size_is_within_the_ceiling():
    """The pager must never offer a size the parser will refuse."""
    for size in PAGE_SIZE_CHOICES:
        assert 1 <= size <= MAX_PAGE_SIZE
        assert parse_page({"page_size": size}, default_sort="x").page_size == size


# ── the envelope a table's footer reads ──────────────────────────────────


def test_the_envelope_carries_the_page_the_total_and_the_count_of_pages():
    body = envelope([1, 2, 3], total=7, page=Page(page=1, page_size=3, sort="x", order="desc"))

    assert body["items"] == [1, 2, 3]
    assert body["total"] == 7
    assert body["pages"] == 3  # 7 rows at 3 a page is three pages, not two


def test_an_exact_division_does_not_produce_a_trailing_empty_page():
    body = envelope([], total=50, page=Page(page=1, page_size=25, sort="x", order="desc"))
    assert body["pages"] == 2


def test_an_empty_result_is_still_one_page():
    """"Page 1 of 0" is not a thing a footer can say."""
    body = envelope([], total=0, page=Page(page=1, page_size=25, sort="x", order="desc"))
    assert body["pages"] == 1


def test_the_envelope_echoes_the_sort_so_the_table_can_show_it():
    body = envelope([], total=0, page=Page(page=2, page_size=10, sort="name", order="asc"))
    assert (body["sort"], body["order"], body["page"], body["page_size"]) == ("name", "asc", 2, 10)


def test_extra_keys_ride_alongside():
    body = envelope([], total=0, page=Page(1, 25, "x", "desc"), facets={"sentiment": []})
    assert body["facets"] == {"sentiment": []}


# ── a path parameter that reaches SQL ────────────────────────────────────


def test_a_uuid_path_parameter_is_validated_before_it_reaches_sql():
    """Otherwise PostgreSQL raises and a client error surfaces as a 500."""
    with pytest.raises(ValidationError) as caught:
        parse_uuid("not-a-uuid", field="record_id")
    assert "record_id" in str(caught.value)


def test_a_real_uuid_passes():
    assert str(parse_uuid("11111111-2222-3333-4444-555555555555")) == (
        "11111111-2222-3333-4444-555555555555"
    )
