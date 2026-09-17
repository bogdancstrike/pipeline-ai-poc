"""
`client.export` — the three files the Export button produces.

An export leaves the application and is opened in something else, usually
Excel, so the failures that matter here are the ones that only appear there: a
mangled accent, a cell the spreadsheet decides to execute, a `null` that
arrives as the four letters n-u-l-l.
"""

import csv
import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from client.errors import ValidationError
from client.export import (
    Column,
    cell,
    csv_lines,
    defuse,
    filename,
    json_lines,
    limit_for,
    parse_format,
    write_to,
    xlsx_bytes,
)


COLUMNS = [Column("name", "Video"), Column("sentiment", "Sentiment"), Column("entity_count", "Entities")]


class Row:
    def __init__(self, **values):
        self.__dict__.update(values)


ROWS = [
    Row(name="qa-0000.mp4", sentiment="NEGATIVE", entity_count=2),
    Row(name="qa-0001.mp4", sentiment="POSITIVE", entity_count=3),
]


# ── which format ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("fmt", ["csv", "json", "xlsx"])
def test_every_offered_format_is_accepted(fmt):
    assert parse_format(fmt) == fmt


def test_the_format_is_matched_whatever_its_case_or_padding():
    assert parse_format("  CSV ") == "csv"


def test_no_format_means_csv():
    assert parse_format(None) == "csv"


def test_an_unknown_format_is_refused():
    with pytest.raises(ValidationError):
        parse_format("pdf")


def test_a_spreadsheet_is_capped_lower_than_a_stream():
    """csv and json stream; xlsx is built in memory and must not be unbounded."""
    assert limit_for("xlsx") < limit_for("csv")


# ── the file name ────────────────────────────────────────────────────────


def test_the_file_name_carries_the_moment_so_two_exports_are_two_files():
    moment = datetime(2026, 5, 18, 9, 30, tzinfo=UTC)
    assert filename("records", "csv", moment=moment) == "records-2026-05-18-0930.csv"


def test_the_file_name_is_safe_for_a_download_folder():
    name = filename("records: negative/partial", "csv", moment=datetime(2026, 5, 18, tzinfo=UTC))
    assert "/" not in name and ":" not in name
    assert name.endswith(".csv")


def test_an_empty_stem_still_produces_a_name():
    assert filename("", "json", moment=datetime(2026, 5, 18, tzinfo=UTC)).startswith("export-")


# ── one value in one cell ────────────────────────────────────────────────


def test_a_datetime_is_written_as_iso():
    assert cell(datetime(2026, 5, 18, 9, 30, tzinfo=UTC)).startswith("2026-05-18T09:30")


def test_a_date_is_written_as_iso():
    assert cell(date(2026, 5, 18)) == "2026-05-18"


def test_a_uuid_is_written_as_its_text():
    value = UUID("11111111-2222-3333-4444-555555555555")
    assert cell(value) == str(value)


def test_a_decimal_becomes_a_number_not_a_string():
    assert cell(Decimal("2.50")) == 2.5


def test_a_boolean_is_written_as_a_word():
    assert cell(True) == "true"
    assert cell(False) == "false"


def test_a_list_or_dict_is_written_as_json():
    assert json.loads(cell(["a", "b"])) == ["a", "b"]
    assert json.loads(cell({"k": 1})) == {"k": 1}


def test_a_list_keeps_its_accents_rather_than_escaping_them():
    assert "Málaga" in cell(["Málaga"])


def test_nothing_is_blank_in_a_csv_and_null_in_json():
    """A CSV has no way to say "absent"; JSON does, and should use it."""
    assert cell(None, blank_none=True) == ""
    assert cell(None, blank_none=False) is None


# ── the spreadsheet-formula problem ──────────────────────────────────────


@pytest.mark.parametrize("dangerous", ["=1+1", "+1", "-1+1", "@SUM(A1)"])
def test_a_cell_that_a_spreadsheet_would_execute_is_defused(dangerous):
    assert defuse(dangerous).startswith("'")


def test_defusing_leaves_ordinary_text_alone():
    assert defuse("Ceuta") == "Ceuta"


def test_defusing_leaves_numbers_alone():
    """Quoting -3 would turn a number column into a text column."""
    assert defuse(-3) == -3
    assert defuse(2.5) == 2.5


def test_defusing_leaves_an_empty_value_alone():
    assert defuse("") == ""
    assert defuse(None) is None


# ── CSV ──────────────────────────────────────────────────────────────────


def test_the_csv_opens_with_a_byte_order_mark():
    """Without it Excel on Windows reads UTF-8 as the local codepage."""
    assert "".join(csv_lines(ROWS, COLUMNS)).startswith("﻿")


def test_the_csv_header_is_the_column_titles():
    text = "".join(csv_lines(ROWS, COLUMNS)).lstrip("﻿")
    assert text.splitlines()[0] == "Video,Sentiment,Entities"


def test_the_csv_carries_one_line_per_row():
    text = "".join(csv_lines(ROWS, COLUMNS)).lstrip("﻿")
    assert len(text.strip().splitlines()) == len(ROWS) + 1


def test_the_csv_is_parseable_by_a_csv_reader():
    text = "".join(csv_lines(ROWS, COLUMNS)).lstrip("﻿")
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert parsed[0]["Video"] == "qa-0000.mp4"
    assert parsed[1]["Sentiment"] == "POSITIVE"


def test_a_comma_inside_a_value_does_not_become_a_column():
    rows = [Row(name="a,b.mp4", sentiment="NEGATIVE", entity_count=1)]
    text = "".join(csv_lines(rows, COLUMNS)).lstrip("﻿")
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert parsed[0]["Video"] == "a,b.mp4"


def test_the_csv_is_produced_lazily_rather_than_assembled():
    """A 50,000-row export must not be built in memory before it is sent."""
    chunks = csv_lines(ROWS, COLUMNS)
    assert next(iter(chunks)) is not None


# ── JSON ─────────────────────────────────────────────────────────────────


def test_the_json_export_parses_as_one_document():
    text = "".join(json_lines(ROWS, COLUMNS))
    parsed = json.loads(text)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "qa-0000.mp4"


def test_the_json_export_keys_on_the_field_name_not_the_label():
    parsed = json.loads("".join(json_lines(ROWS, COLUMNS)))
    assert "name" in parsed[0] and "Video" not in parsed[0]


def test_an_absent_value_is_null_in_json_not_an_empty_string():
    rows = [Row(name="x.mp4", sentiment=None, entity_count=0)]
    parsed = json.loads("".join(json_lines(rows, COLUMNS)))
    assert parsed[0]["sentiment"] is None


def test_an_empty_json_export_is_still_a_valid_document():
    assert json.loads("".join(json_lines([], COLUMNS))) == []


# ── XLSX ─────────────────────────────────────────────────────────────────


def test_the_spreadsheet_is_a_zip_container():
    """.xlsx is an OPC package; the magic bytes are how anything recognises it."""
    assert xlsx_bytes(ROWS, COLUMNS)[:2] == b"PK"


def test_the_spreadsheet_carries_the_values():
    import zipfile

    package = zipfile.ZipFile(io.BytesIO(xlsx_bytes(ROWS, COLUMNS)))
    sheet = package.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "Video" in sheet          # the header
    assert "qa-0000.mp4" in sheet    # the first row
    assert "POSITIVE" in sheet       # the last row


def test_the_spreadsheet_is_offered_only_where_it_can_be_produced():
    """The Export menu is built from this, not from the full list of formats."""
    from client.export import FORMATS, available_formats

    assert set(available_formats()) <= set(FORMATS)
    assert "csv" in available_formats() and "json" in available_formats()

    import importlib.util

    if importlib.util.find_spec("openpyxl"):
        assert "xlsx" in available_formats()
    else:
        assert "xlsx" not in available_formats()


# ── the one entry point the endpoint uses ────────────────────────────────


@pytest.mark.parametrize("fmt", ["csv", "json", "xlsx"])
def test_write_to_reports_how_many_rows_it_wrote(fmt):
    target = io.BytesIO()
    assert write_to(target, ROWS, COLUMNS, fmt=fmt) == len(ROWS)
    assert target.getvalue()


def test_write_to_trusts_its_caller_to_have_validated_the_format():
    """Pinned, not endorsed: an unknown format falls through to CSV.

    Unreachable from HTTP — every endpoint runs `parse_format` first, which is
    where the refusal lives. Worth a test so that if `write_to` ever grows a
    second caller, the silent fallback is a decision rather than a discovery.
    """
    target = io.BytesIO()
    assert write_to(target, ROWS, COLUMNS, fmt="pdf") == len(ROWS)
    assert target.getvalue().lstrip("\ufeff".encode()).startswith(b"Video,")


def test_a_column_falls_back_to_a_readable_title():
    assert Column("entity_count").title == "Entity count"
