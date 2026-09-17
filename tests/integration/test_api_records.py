"""
`/client/records*` — the explorer's one question, asked over HTTP.

The whole screen is a single request, so these are the tests that decide
whether the Records page can be trusted: the total, the facets, the paging, the
sort and the sentence describing what ran all travel in one envelope, and a
disagreement between any two of them is a disagreement the reader can see.
"""

import pytest

from support import corpus, live

pytestmark = pytest.mark.live


def search(**payload):
    answer = live.post("/client/records/search", payload)
    assert answer.ok, answer.text[:300]
    return answer.body


# ── the envelope ─────────────────────────────────────────────────────────


def test_a_search_answers_the_page_the_total_and_the_catalogue(seeded_only, expected):
    body = search(filters=seeded_only, page_size=10)

    assert body["total"] == expected["total"]
    assert len(body["items"]) == 10
    assert body["page"] == 1
    assert body["pages"] == expected["total"] // 10
    assert body["columns"]
    assert body["fields"], "the frontend builds its controls from this"


def test_every_row_carries_the_columns_that_were_asked_for(seeded_only):
    body = search(filters=seeded_only, columns=["name", "sentiment", "entity_count"], page_size=3)

    for row in body["items"]:
        assert set(row) >= {"id", "name", "sentiment", "entity_count"}


def test_the_default_columns_are_the_explorers_own(seeded_only):
    body = search(filters=seeded_only, page_size=1)
    assert "name" in body["columns"] and "analysed_at" in body["columns"]


def test_a_row_carries_a_summary_preview_for_the_table(seeded_only):
    body = search(filters=seeded_only, page_size=1)
    assert body["items"][0]["summary_preview"]


# ── paging ───────────────────────────────────────────────────────────────


def test_the_second_page_holds_different_records(seeded_only):
    first = search(filters=seeded_only, page=1, page_size=5, sort="id", order="asc")
    second = search(filters=seeded_only, page=2, page_size=5, sort="id", order="asc")

    assert {row["id"] for row in first["items"]}.isdisjoint({row["id"] for row in second["items"]})


def test_paging_through_the_corpus_visits_every_record_exactly_once(seeded_only, expected):
    seen = []
    for page in range(1, expected["total"] // 25 + 2):
        body = search(filters=seeded_only, page=page, page_size=25, sort="id", order="asc")
        seen.extend(row["id"] for row in body["items"])

    assert len(seen) == expected["total"]
    assert len(set(seen)) == expected["total"]


def test_a_page_past_the_end_is_empty_rather_than_an_error(seeded_only):
    body = search(filters=seeded_only, page=9999, page_size=25)
    assert body["items"] == []
    assert body["total"] > 0


@pytest.mark.parametrize("size", [1, 10, 25, 200])
def test_every_offered_page_size_is_accepted(seeded_only, size):
    assert len(search(filters=seeded_only, page_size=size)["items"]) <= size


def test_a_page_size_past_the_ceiling_is_refused():
    answer = live.post("/client/records/search", {"page_size": 5000})
    assert answer.status == 400
    assert "page_size" in answer.text


# ── sorting ──────────────────────────────────────────────────────────────


def test_sorting_is_done_by_the_database_not_the_page(seeded_only):
    """A table that sorts its own 25 rows presents them as if it saw all 120."""
    ascending = search(filters=seeded_only, sort="name", order="asc", page_size=5)
    descending = search(filters=seeded_only, sort="name", order="desc", page_size=5)

    names = [row["name"] for row in ascending["items"]]
    assert names == sorted(names)
    assert ascending["items"][0]["name"] != descending["items"][0]["name"]


def test_the_newest_record_is_first_by_default(seeded_only):
    body = search(filters=seeded_only, page_size=2)
    assert body["items"][0]["analysed_at"] >= body["items"][1]["analysed_at"]


def test_sorting_by_a_number_orders_numerically(seeded_only):
    body = search(filters=seeded_only, sort="entity_count", order="desc", page_size=10)
    counts = [row["entity_count"] for row in body["items"]]
    assert counts == sorted(counts, reverse=True)


def test_an_unknown_sort_field_falls_back_rather_than_failing(seeded_only):
    body = search(filters=seeded_only, sort="; DROP TABLE video_records", page_size=1)
    assert body["total"] > 0


# ── the filter bar ───────────────────────────────────────────────────────


def test_a_sentiment_filter_narrows_to_that_sentiment(seeded_only, expected):
    body = search(filters={**seeded_only, "sentiment": "NEGATIVE"}, page_size=5)

    assert body["total"] == expected["sentiments"]["NEGATIVE"]
    assert {row["sentiment"] for row in body["items"]} == {"NEGATIVE"}


def test_two_values_in_one_filter_widen_it(seeded_only, expected):
    body = search(filters={**seeded_only, "sentiment": "NEGATIVE,POSITIVE"})
    assert body["total"] == (
        expected["sentiments"]["NEGATIVE"] + expected["sentiments"]["POSITIVE"]
    )


def test_a_status_filter_finds_the_partial_records(seeded_only, expected):
    body = search(filters={**seeded_only, "status": "partial"}, page_size=5)

    assert body["total"] == expected["statuses"]["partial"]
    assert all(row["status"] == "partial" for row in body["items"])


def test_two_filters_narrow_together(seeded_only, expected):
    both = search(filters={**seeded_only, "sentiment": "NEGATIVE", "status": "partial"})
    one = search(filters={**seeded_only, "sentiment": "NEGATIVE"})

    assert both["total"] <= one["total"]


def test_an_operator_suffix_works_over_http(seeded_only):
    body = search(filters={**seeded_only, "person_count__gt": 1})
    assert body["total"] > 0
    assert all(row["person_count"] > 1 for row in body["items"])


def test_a_filter_matching_nothing_answers_an_empty_page(seeded_only):
    body = search(filters={**seeded_only, "sentiment": "ECSTATIC"})
    assert body["total"] == 0
    assert body["items"] == []


# ── free text ────────────────────────────────────────────────────────────


def test_free_text_finds_the_one_record_that_carries_the_term(seeded_only):
    body = search(filters=seeded_only, query_text="Record 7:")
    assert body["total"] == 1
    assert body["items"][0]["id"] == corpus.ids(8)[7]


def test_free_text_sweeps_the_transcript_not_only_the_summary(seeded_only):
    """A word that appears only in what was heard still finds the video."""
    body = search(filters=seeded_only, query_text="Speaker two answers briefly")
    assert body["total"] > 0


def test_free_text_sweeps_the_on_screen_text(seeded_only):
    assert search(filters=seeded_only, query_text="BREAKING")["total"] > 0


def test_free_text_is_case_insensitive(seeded_only):
    lower = search(filters=seeded_only, query_text="breakwater")["total"]
    upper = search(filters=seeded_only, query_text="BREAKWATER")["total"]
    assert lower == upper > 0


def test_the_search_echoes_the_term_that_actually_ran(seeded_only):
    """The box and the results differ while a request is in flight."""
    assert search(filters=seeded_only, query_text="ceuta")["query_text"] == "ceuta"


def test_free_text_that_matches_nothing_is_an_empty_page(seeded_only):
    assert search(filters=seeded_only, query_text="zzzz-no-such-word")["total"] == 0


# ── facets ───────────────────────────────────────────────────────────────


def test_facets_are_only_computed_when_they_are_asked_for(seeded_only):
    assert search(filters=seeded_only, facets=False)["facets"] == {}


def test_the_facet_counts_match_the_corpus(seeded_only, expected):
    facets = search(filters=seeded_only, facets=True)["facets"]
    sentiment = {entry["value"]: entry["count"] for entry in facets["sentiment"]}

    assert sentiment == expected["sentiments"]


def test_the_facets_narrow_with_the_question(seeded_only):
    """Menus built from the data, not from a list that drifts from it."""
    facets = search(filters={**seeded_only, "sentiment": "NEGATIVE"}, facets=True)["facets"]
    assert {entry["value"] for entry in facets["sentiment"]} == {"NEGATIVE"}


def test_the_model_facet_offers_every_model_in_the_corpus(seeded_only, expected):
    facets = search(filters=seeded_only, facets=True)["facets"]
    assert {entry["value"] for entry in facets["model"]} == set(expected["models"])


# ── the advanced condition tree ──────────────────────────────────────────


def rule(field, operator, value):
    return {"type": "rule", "properties": {"field": field, "operator": operator, "value": value}}


def tree(*rules, conjunction="AND"):
    return {
        "type": "group",
        "properties": {"conjunction": conjunction},
        "children1": {f"r{index}": item for index, item in enumerate(rules)},
    }


def test_a_condition_tree_narrows_and_says_what_it_asked(seeded_only, expected):
    body = search(
        filters=seeded_only,
        condition_tree=tree(rule("sentiment", "select_equals", ["NEGATIVE"])),
    )

    assert body["total"] == expected["sentiments"]["NEGATIVE"]
    assert "Sentiment" in body["condition_text"]
    assert body["rule_count"] == 1


def test_an_or_group_widens(seeded_only, expected):
    body = search(
        filters=seeded_only,
        condition_tree=tree(
            rule("sentiment", "select_equals", ["NEGATIVE"]),
            rule("sentiment", "select_equals", ["POSITIVE"]),
            conjunction="OR",
        ),
    )
    assert body["total"] == (
        expected["sentiments"]["NEGATIVE"] + expected["sentiments"]["POSITIVE"]
    )


def test_the_described_condition_matches_the_rows_that_came_back(seeded_only):
    body = search(
        filters=seeded_only,
        condition_tree=tree(
            rule("sentiment", "select_equals", ["NEGATIVE"]),
            rule("person_count", "greater", 0),
        ),
        page_size=50,
    )

    assert "AND" in body["condition_text"]
    for row in body["items"]:
        assert row["sentiment"] == "NEGATIVE"
        assert row["person_count"] > 0


def test_a_half_built_rule_does_not_blank_the_table(seeded_only, expected):
    """The editor sends the tree on every keystroke."""
    body = search(filters=seeded_only, condition_tree=tree(rule("sentiment", "select_equals", [])))
    assert body["total"] == expected["total"]


def test_an_unknown_field_in_a_tree_is_a_400_that_names_it(seeded_only):
    answer = live.post(
        "/client/records/search",
        {"filters": seeded_only, "condition_tree": tree(rule("salary", "equal", "x"))},
    )
    assert answer.status == 400
    assert "salary" in answer.text


def test_a_tree_that_is_not_an_object_is_refused():
    answer = live.post("/client/records/search", {"condition_tree": "everything"})
    assert answer.status == 400


# ── one record ───────────────────────────────────────────────────────────


def test_a_record_carries_every_enrichment_the_panels_render(seeded_only):
    record_id = corpus.ids(1)[0]
    answer = live.get(f"/client/records/{record_id}")
    assert answer.ok

    body = answer.body
    for key in ("summary", "description", "transcript", "ocr_text", "entities",
                "persons", "sentiment", "calls", "document", "video"):
        assert key in body, key


def test_a_record_carries_its_call_provenance(seeded_only):
    body = live.get(f"/client/records/{corpus.ids(1)[0]}").body
    services = {call["service"] for call in body["calls"]}
    assert "face-match-main" in services and "summary" in services


def test_a_partial_record_says_which_service_did_not_answer(seeded_only):
    partial = search(filters={**seeded_only, "status": "partial"}, page_size=1)["items"][0]
    body = live.get(f"/client/records/{partial['id']}").body

    assert body["failed_services"]
    assert body["errors"]
    assert body["status"] == "partial"


def test_the_entities_are_split_into_a_type_and_a_value(seeded_only):
    body = live.get(f"/client/records/{corpus.ids(1)[0]}").body
    for entity in body["entities"]:
        assert entity["type"] and entity["value"]


def test_a_record_that_does_not_exist_is_a_404():
    assert live.get("/client/records/no-such-record").status == 404


def test_the_record_says_whether_its_video_can_be_played_here(seeded_only):
    video = live.get(f"/client/records/{corpus.ids(1)[0]}").body["video"]
    assert "playable" in video
    # The QA corpus names paths that are not mounted, so this is the honest no.
    assert video["playable"] is False


# ── related records ──────────────────────────────────────────────────────


def test_related_records_share_an_entity(seeded_only):
    answer = live.get(f"/client/records/{corpus.ids(1)[0]}/related")
    assert answer.ok

    for item in answer.body["items"]:
        assert item["shared"], "a related record has to say what it shares"


def test_a_record_is_not_related_to_itself(seeded_only):
    record_id = corpus.ids(1)[0]
    body = live.get(f"/client/records/{record_id}/related").body
    assert record_id not in {item["id"] for item in body["items"]}


# ── the simple list endpoint ─────────────────────────────────────────────


def test_the_list_endpoint_takes_its_filters_from_the_query_string(seeded_only):
    answer = live.get("/client/records?sentiment=NEGATIVE&page_size=5")
    assert answer.ok
    assert all(row["sentiment"] == "NEGATIVE" for row in answer.body["items"])


def test_the_list_endpoint_pages(seeded_only):
    answer = live.get("/client/records?page=2&page_size=5&sort=id&order=asc")
    assert answer.ok
    assert answer.body["page"] == 2
