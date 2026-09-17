"""
Downloads, the field catalogue, health, and the error contract.

An export leaves the application, so the headers matter as much as the bytes:
a browser that is not told the file name saves `export` with no extension, and
one that is not told the type opens a spreadsheet as text.
"""

import csv
import io
import json
import zipfile

import pytest

from support import corpus, live

pytestmark = pytest.mark.live


def export(fmt="csv", **payload):
    body = json.dumps({"format": fmt, **payload}).encode("utf-8")
    import urllib.request

    request = urllib.request.Request(
        f"{live.API_BASE}/client/records/export",
        data=body,
        headers={"content-type": "application/json", "accept": "*/*"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status, response.read(), response.headers


# ── CSV ──────────────────────────────────────────────────────────────────


def test_a_csv_export_is_a_csv_a_spreadsheet_can_open(seeded_only):
    status, blob, headers = export("csv", filters=seeded_only, columns=["name", "sentiment"])

    assert status == 200
    assert "text/csv" in headers["content-type"]
    assert blob.startswith(b"\xef\xbb\xbf"), "the BOM Excel needs on Windows"


def test_the_csv_carries_a_header_and_the_rows(seeded_only):
    _, blob, _ = export("csv", filters=seeded_only, columns=["name", "sentiment"])
    rows = list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))

    assert len(rows) > 0
    assert set(rows[0]) == {"Video", "Sentiment"}


def test_the_export_carries_the_same_question_as_the_table(seeded_only, expected):
    _, blob, _ = export("csv", filters={**seeded_only, "sentiment": "NEGATIVE"}, columns=["sentiment"])
    rows = list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))

    assert len(rows) == expected["sentiments"]["NEGATIVE"]
    assert {row["Sentiment"] for row in rows} == {"NEGATIVE"}


def test_the_export_honours_a_condition_tree(seeded_only, expected):
    _, blob, _ = export(
        "csv",
        filters=seeded_only,
        columns=["sentiment"],
        condition_tree={
            "type": "group",
            "properties": {"conjunction": "AND"},
            "children1": {
                "r0": {
                    "type": "rule",
                    "properties": {"field": "sentiment", "operator": "select_equals",
                                   "value": ["POSITIVE"]},
                }
            },
        },
    )
    rows = list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
    assert len(rows) == expected["sentiments"]["POSITIVE"]


def test_the_export_is_not_capped_at_one_page(seeded_only, expected):
    """The button says "export these records", not "export this page"."""
    _, blob, _ = export("csv", filters=seeded_only, columns=["name"], page_size=5)
    rows = list(csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))))
    assert len(rows) == expected["total"]


def test_the_download_names_the_file(seeded_only):
    _, _, headers = export("csv", filters=seeded_only, columns=["name"])
    disposition = headers.get("content-disposition", "")

    assert "attachment" in disposition
    assert ".csv" in disposition


def test_the_export_is_ordered_the_way_it_was_asked_for(seeded_only):
    _, blob, _ = export("csv", filters=seeded_only, columns=["name"], sort="name", order="asc")
    rows = [row["Video"] for row in csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))]
    assert rows == sorted(rows)


# ── JSON ─────────────────────────────────────────────────────────────────


def test_a_json_export_parses_as_one_document(seeded_only, expected):
    status, blob, headers = export("json", filters=seeded_only, columns=["name", "sentiment"])

    assert status == 200
    assert "application/json" in headers["content-type"]

    parsed = json.loads(blob)
    assert len(parsed) == expected["total"]
    assert set(parsed[0]) == {"name", "sentiment"}


# ── XLSX ─────────────────────────────────────────────────────────────────


def test_an_xlsx_export_is_a_workbook(seeded_only):
    """Regression: openpyxl was undeclared, so this used to answer 400."""
    status, blob, headers = export("xlsx", filters=seeded_only, columns=["name", "sentiment"])

    assert status == 200, blob[:200]
    assert "spreadsheetml" in headers["content-type"]
    assert blob[:2] == b"PK"

    package = zipfile.ZipFile(io.BytesIO(blob))
    assert "xl/worksheets/sheet1.xml" in package.namelist()


def test_every_advertised_format_can_actually_be_produced(seeded_only):
    """The Export menu is built from this list."""
    for fmt in live.get("/client/meta").body["export_formats"]:
        status, blob, _ = export(fmt, filters=seeded_only, columns=["name"], page_size=5)
        assert status == 200, f"{fmt} is advertised but answered {status}"
        assert blob


def test_a_format_nobody_offers_is_refused():
    """Regression: the format was parsed outside the error guard, so this was a 500."""
    answer = live.post("/client/records/export", {"format": "pdf"})

    assert answer.status == 400
    assert "pdf" in answer.text
    assert "csv" in answer.text, "the refusal has to name what would work"


def test_an_undeclared_export_column_is_a_400_not_a_500():
    answer = live.post("/client/records/export", {"columns": ["salary"]})
    assert answer.status == 400


def test_a_malformed_condition_tree_in_an_export_is_a_400_not_a_500():
    answer = live.post(
        "/client/records/export",
        {"condition_tree": {"type": "group", "properties": {"conjunction": "XOR"},
                            "children1": {"r0": {"type": "rule", "properties": {
                                "field": "sentiment", "operator": "select_equals",
                                "value": ["NEGATIVE"]}}}}},
    )
    assert answer.status == 400


# ── the catalogue the frontend builds itself from ────────────────────────


def test_meta_publishes_the_fields_the_query_builder_renders():
    body = live.get("/client/meta").body
    fields = {field["name"]: field for field in body["fields"]}

    assert "sentiment" in fields
    assert fields["sentiment"]["kind"] == "enum"
    assert "NEGATIVE" in fields["sentiment"]["choices"]
    assert fields["sentiment"]["operators"]


def test_meta_publishes_the_page_sizes_the_pager_offers():
    assert live.get("/client/meta").body["page_sizes"]


def test_meta_publishes_the_sentiments_and_statuses_the_menus_show():
    body = live.get("/client/meta").body
    assert set(body["sentiments"]) == {"POSITIVE", "NEUTRAL", "NEGATIVE"}
    assert set(body["statuses"]) == {"analysed", "partial"}


def test_every_field_the_table_defaults_to_is_in_the_catalogue():
    body = live.get("/client/meta").body
    names = {field["name"] for field in body["fields"]}
    search = live.post("/client/records/search", {"page_size": 1}).body
    assert set(search["columns"]) <= names


def test_no_field_offers_an_operator_the_backend_cannot_honour():
    """The builder is generated from this; an extra operator is a 400 per click."""
    from client.query import OPERATORS

    for field in live.get("/client/meta").body["fields"]:
        assert set(field["operators"]) <= OPERATORS, field["name"]


# ── health ───────────────────────────────────────────────────────────────


def test_health_says_which_database_it_is_talking_to():
    body = live.get("/client/health").body

    assert body["status"] == "ok"
    assert body["url"]
    assert "***" in body["url"], "the password must not be in a health answer"


def test_health_counts_what_is_stored(expected):
    body = live.get("/client/health").body
    assert body["records"] >= expected["total"]
    assert body["calls"] >= expected["total"]
    assert body["tables"]


# ── the video endpoint ───────────────────────────────────────────────────


def test_a_video_that_is_not_mounted_here_is_a_404_that_explains_itself():
    answer = live.get(f"/client/records/{corpus.ids(1)[0]}/video")

    assert answer.status == 404
    assert "VIDEO_SEARCH_DIRS" in answer.text
    assert "search_dirs" in answer.text


def test_the_video_endpoint_of_a_record_that_does_not_exist_is_a_404():
    assert live.get("/client/records/no-such-record/video").status == 404


# ── the error contract ───────────────────────────────────────────────────


def test_a_bad_request_answers_json_not_html():
    answer = live.post("/client/records/search", {"page_size": -1})
    assert answer.status == 400
    assert answer.body is not None, "an error a frontend cannot parse is a 500 to it"


def test_an_error_carries_a_message_a_person_can_act_on():
    answer = live.post("/client/records/search", {"page_size": 99999})
    assert "page_size" in answer.text


def test_a_route_that_does_not_exist_is_a_404():
    assert live.get("/client/no-such-endpoint").status == 404


def test_the_api_documents_itself():
    """The Swagger the header's API button opens."""
    answer = live.get("/swagger.json")
    assert answer.ok
    assert "paths" in answer.body
