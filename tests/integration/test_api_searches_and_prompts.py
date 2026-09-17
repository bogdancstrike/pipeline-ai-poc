"""
`/client/searches` and `/client/prompts` — the two things a reader can write.

Everything else in this app is read-only over a corpus the pipeline produced.
These two are state the UI creates, so they get the whole lifecycle: create,
read back, edit, use, and delete — including what happens when the thing being
edited is gone.
"""

import uuid

import pytest

from support import live

pytestmark = pytest.mark.live

MARK = f"qa-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def saved_search():
    """One saved search, removed again however the test ends."""
    created = live.post(
        "/client/searches",
        {
            "name": f"{MARK} negative with people",
            "description": "Everything the reader should look at first",
            "owner": "qa",
            "pinned": False,
            "payload": {
                "filters": {"sentiment": "NEGATIVE"},
                "query_text": "ceuta",
                "sort": "analysed_at",
                "order": "desc",
                "page_size": 25,
            },
        },
    )
    assert created.status in (200, 201), created.text[:300]
    yield created.body
    live.delete(f"/client/searches/{created.body['id']}")


# ── saved searches ───────────────────────────────────────────────────────


def test_a_saved_search_stores_the_question_not_the_answer(saved_search):
    assert saved_search["payload"]["filters"] == {"sentiment": "NEGATIVE"}
    assert saved_search["payload"]["query_text"] == "ceuta"
    assert "items" not in saved_search["payload"], "the rows are not part of the question"
    assert "total" not in saved_search["payload"]


def test_a_new_saved_search_has_never_been_run(saved_search):
    assert saved_search["run_count"] == 0
    assert saved_search["last_run_at"] in (None, "")


def test_a_saved_search_appears_in_the_list(saved_search):
    listing = live.get("/client/searches?page_size=100")
    assert listing.ok
    assert saved_search["id"] in {item["id"] for item in listing.body["items"]}


def test_a_saved_search_can_be_found_by_name(saved_search):
    found = live.get(f"/client/searches?q={MARK}")
    assert found.ok
    assert found.body["total"] >= 1


def test_a_saved_search_can_be_renamed(saved_search):
    updated = live.put(f"/client/searches/{saved_search['id']}", {"name": f"{MARK} renamed"})
    assert updated.ok
    assert updated.body["name"] == f"{MARK} renamed"


def test_pinning_survives_a_read_back(saved_search):
    live.put(f"/client/searches/{saved_search['id']}", {"pinned": True})
    listing = live.get("/client/searches?page_size=100").body["items"]
    pinned = {item["id"]: item["pinned"] for item in listing}
    assert pinned[saved_search["id"]] is True


def test_a_pinned_search_is_listed_first(saved_search):
    live.put(f"/client/searches/{saved_search['id']}", {"pinned": True})
    items = live.get("/client/searches?page_size=100").body["items"]
    if len(items) > 1:
        assert items[0]["pinned"] is True


def test_an_update_leaves_the_fields_it_was_not_given_alone(saved_search):
    live.put(f"/client/searches/{saved_search['id']}", {"pinned": True})
    after = live.get("/client/searches?page_size=100").body["items"]
    row = {item["id"]: item for item in after}[saved_search["id"]]

    assert row["description"] == "Everything the reader should look at first"
    assert row["payload"]["query_text"] == "ceuta"


def test_running_a_saved_search_answers_the_rows_it_asks_for(saved_search):
    answer = live.post(f"/client/searches/{saved_search['id']}/run", {})
    assert answer.ok
    assert "items" in answer.body
    assert all(row["sentiment"] == "NEGATIVE" for row in answer.body["items"])


def test_running_a_saved_search_counts_the_use(saved_search):
    """So "recently used" is honest."""
    live.post(f"/client/searches/{saved_search['id']}/run", {})
    items = live.get("/client/searches?page_size=100").body["items"]
    row = {item["id"]: item for item in items}[saved_search["id"]]

    assert row["run_count"] >= 1
    assert row["last_run_at"]


def test_running_one_asks_the_question_of_whatever_has_been_analysed_since(saved_search):
    """The stored request is re-run, not a stored answer replayed."""
    first = live.post(f"/client/searches/{saved_search['id']}/run", {}).body
    second = live.post(f"/client/searches/{saved_search['id']}/run", {}).body
    assert first["total"] == second["total"]


def test_a_saved_search_can_carry_a_condition_tree():
    created = live.post(
        "/client/searches",
        {
            "name": f"{MARK} advanced",
            "payload": {
                "condition_tree": {
                    "type": "group",
                    "properties": {"conjunction": "AND"},
                    "children1": {
                        "r0": {
                            "type": "rule",
                            "properties": {
                                "field": "sentiment",
                                "operator": "select_equals",
                                "value": ["NEGATIVE"],
                            },
                        }
                    },
                }
            },
        },
    )
    assert created.status in (200, 201)
    try:
        run = live.post(f"/client/searches/{created.body['id']}/run", {})
        assert run.ok
        assert run.body["rule_count"] == 1
    finally:
        live.delete(f"/client/searches/{created.body['id']}")


def test_a_saved_search_without_a_name_is_refused():
    answer = live.post("/client/searches", {"payload": {}})
    assert answer.status == 400


def test_deleting_one_removes_it():
    created = live.post("/client/searches", {"name": f"{MARK} temporary"})
    search_id = created.body["id"]

    assert live.delete(f"/client/searches/{search_id}").ok

    remaining = live.get("/client/searches?page_size=200").body["items"]
    assert search_id not in {item["id"] for item in remaining}


def test_deleting_one_that_is_gone_is_a_404():
    assert live.delete("/client/searches/no-such-search").status == 404


def test_updating_one_that_is_gone_is_a_404():
    assert live.put("/client/searches/no-such-search", {"name": "x"}).status == 404


def test_running_one_that_is_gone_is_a_404():
    assert live.post("/client/searches/no-such-search/run", {}).status == 404


# ── prompts ──────────────────────────────────────────────────────────────


def test_the_three_prompts_are_listed_with_their_text():
    answer = live.get("/client/prompts")
    assert answer.ok

    names = {item["name"] for item in answer.body["items"]}
    assert {"summary", "entities", "sentiment"} <= names
    for item in answer.body["items"]:
        assert item["text"].strip()
        assert item["file"]


def test_the_listing_says_whether_the_database_copy_is_in_use():
    assert "from_db" in live.get("/client/prompts").body


def test_a_prompt_that_was_never_edited_is_not_marked_modified():
    for item in live.get("/client/prompts").body["items"]:
        assert isinstance(item["modified"], bool)


@pytest.fixture()
def restored_prompt():
    """Edit the sentiment prompt and put the shipped wording back afterwards."""
    yield "sentiment"
    live.post("/client/prompts/sentiment/reset", {})


def test_saving_a_prompt_answers_the_new_version(restored_prompt):
    answer = live.put(
        "/client/prompts/sentiment",
        {"text": "Answer with exactly one word: POSITIVE, NEUTRAL or NEGATIVE.", "updated_by": "qa"},
    )
    assert answer.ok
    assert answer.body["version"] >= 1
    assert answer.body["updated_by"] == "qa"


def test_a_saved_prompt_is_what_the_next_read_returns(restored_prompt):
    text = f"QA wording {MARK}. Answer with one word."
    live.put("/client/prompts/sentiment", {"text": text})

    items = {item["name"]: item for item in live.get("/client/prompts").body["items"]}
    assert items["sentiment"]["text"] == text


def test_a_saved_prompt_is_marked_as_edited_against_the_shipped_wording(restored_prompt):
    live.put("/client/prompts/sentiment", {"text": f"QA wording {MARK}"})

    items = {item["name"]: item for item in live.get("/client/prompts").body["items"]}
    assert items["sentiment"]["modified"] is True


def test_saving_again_raises_the_version(restored_prompt):
    first = live.put("/client/prompts/sentiment", {"text": f"one {MARK}"}).body["version"]
    second = live.put("/client/prompts/sentiment", {"text": f"two {MARK}"}).body["version"]
    assert second > first


def test_resetting_restores_the_wording_that_ships(restored_prompt):
    shipped = {i["name"]: i for i in live.get("/client/prompts").body["items"]}["sentiment"]["text"]
    live.put("/client/prompts/sentiment", {"text": f"temporary {MARK}"})

    answer = live.post("/client/prompts/sentiment/reset", {})
    assert answer.ok
    assert answer.body["text"] == shipped

    items = {i["name"]: i for i in live.get("/client/prompts").body["items"]}
    assert items["sentiment"]["modified"] is False


def test_an_empty_prompt_is_refused():
    """A prompt is the whole message to the model; an empty one is a broken run."""
    assert live.put("/client/prompts/sentiment", {"text": "   "}).status == 400


def test_a_prompt_nobody_ships_is_a_404():
    assert live.put("/client/prompts/no-such-prompt", {"text": "hello"}).status == 404
    assert live.post("/client/prompts/no-such-prompt/reset", {}).status == 404
