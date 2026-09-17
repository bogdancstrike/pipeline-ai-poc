"""Exports (§30): CSV, JSON and XLSX of *the current question*.

Three properties this file exists to guarantee, and each of them is a mistake
somebody makes when they write an export by hand:

**It exports the question, not the page.** A reader who filtered 200 000 rows
down to 340 and pressed Export wants 340 rows, not the 25 they can see. The
callers here pass the same statement the list endpoint built, minus its
LIMIT/OFFSET, so the file and the screen can never disagree about what was
asked.

**It streams.** A 50 000-row CSV assembled in memory is 50 000 rows of RAM per
concurrent export, on a gevent worker that is also serving everything else.
Rows are read from PostgreSQL in batches and written out as they arrive, so the
process holds a batch rather than a file. XLSX is the exception the format
forces — a spreadsheet is a zip container and cannot be produced incrementally
— which is why it has a lower row cap of its own.

**It does not hand Excel a formula.** A cell whose text begins with `=`, `+`,
`-` or `@` is *executed* when the file is opened, and the values in it came
from whoever typed them into the application. Prefixing those with a quote is
the standard mitigation, and the reason a CSV export is a security surface at
all (§76).
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, BinaryIO
from uuid import UUID

from client.clock import now
from client.errors import ValidationError

FORMATS = ("csv", "json", "xlsx")


def available_formats() -> tuple[str, ...]:
    """The formats this deployment can actually produce.

    `xlsx` needs openpyxl. It is declared in requirements.txt, but a menu built
    from `FORMATS` on a deployment that dropped it offers a button that answers
    400 every time — so what is advertised is what imports, checked once.
    """
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            _AVAILABLE = tuple(f for f in FORMATS if f != "xlsx")
        else:
            _AVAILABLE = FORMATS
    return _AVAILABLE


_AVAILABLE: tuple[str, ...] | None = None

#: Rows above which an export must become a background job (§23) rather than a
#: request somebody's browser is holding open. Chosen to be comfortably longer
#: than a spreadsheet anybody opens and comfortably shorter than a request that
#: outlives a proxy timeout.
MAX_ROWS = 50_000

#: XLSX has to be finished before the first byte can be sent, so its ceiling is
#: what one worker should be willing to hold, not what a stream can carry.
MAX_XLSX_ROWS = 20_000

#: How many rows to pull from the cursor at a time. Large enough that the
#: round trips do not dominate, small enough that a batch is not the file.
BATCH = 500

#: The characters Excel and LibreOffice treat as the start of a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True, slots=True)
class Column:
    """One column of the file: where to read it, and what to call it."""

    name: str
    label: str = ""

    @property
    def title(self) -> str:
        if self.label:
            return self.label
        spaced = self.name.replace("_", " ")
        return spaced[:1].upper() + spaced[1:]


def parse_format(raw: Any, *, default: str = "csv") -> str:
    value = str(raw or default).strip().lower()
    if value not in FORMATS:
        raise ValidationError(
            f"{value!r} is not an export format; use one of " + ", ".join(FORMATS),
            details={"format": value, "supported": list(FORMATS)},
        )
    return value


def limit_for(fmt: str) -> int:
    return MAX_XLSX_ROWS if fmt == "xlsx" else MAX_ROWS


def filename(stem: str, fmt: str, *, moment: datetime | None = None) -> str:
    """`tickets-2026-09-04-1712.csv` — sortable, and says what it holds.

    A downloads folder with four files called `export.csv` is a downloads
    folder where nobody can tell which one was the filtered one.
    """
    stamp = (moment or now()).strftime("%Y-%m-%d-%H%M")
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in stem).strip("-")
    return f"{safe or 'export'}-{stamp}.{fmt}"


# ── value rendering ──────────────────────────────────────────────────────


def cell(value: Any, *, blank_none: bool = True) -> Any:
    """One Python value as something a cell can hold.

    `blank_none` is what separates the two destinations: a CSV cell has no way
    to say "no value" other than being empty, while JSON has `null` — and a
    consumer parsing the JSON should not have to guess whether `""` meant an
    empty string or a missing one.
    """
    if value is None:
        return "" if blank_none else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str, ensure_ascii=False)
    return value


def defuse(value: Any) -> Any:
    """Stop a spreadsheet from executing a cell that came from a text box.

    Only text is at risk, and only at the start of the cell. Numbers are left
    alone: quoting `-3` would turn a number column into a text column, which is
    a different kind of broken export.
    """
    if not isinstance(value, str) or not value:
        return value
    return f"'{value}" if value[0] in _FORMULA_PREFIXES else value


def _row_values(row: Any, columns: list[Column], *, blank_none: bool = True) -> list[Any]:
    """A row — ORM object or mapping — as the cells of one line."""
    read = (lambda name: row.get(name)) if isinstance(row, dict) else (
        lambda name: getattr(row, name, None)
    )
    return [cell(read(column.name), blank_none=blank_none) for column in columns]


# ── writers ──────────────────────────────────────────────────────────────


def csv_lines(rows: Iterable[Any], columns: list[Column]) -> Iterator[str]:
    """A CSV, one chunk at a time, starting with a BOM.

    The BOM is not decoration: Excel on Windows reads a UTF-8 CSV without one
    as the local codepage, and every accented name in the file comes out
    mangled. It is the single most reported "your export is broken" bug.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    def flush() -> str:
        text = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return text

    yield "﻿"
    writer.writerow([column.title for column in columns])
    yield flush()

    for row in rows:
        writer.writerow([defuse(value) for value in _row_values(row, columns)])
        yield flush()


def json_lines(rows: Iterable[Any], columns: list[Column]) -> Iterator[str]:
    """A JSON array, streamed element by element.

    A real array rather than newline-delimited JSON, because the caller asked
    for `.json` and every tool that reads one expects to be able to parse the
    whole file. Built by hand rather than by `json.dumps(list(rows))` for the
    same reason the CSV is: the list is the thing we are refusing to hold.
    """
    yield "["
    first = True
    for row in rows:
        values = _row_values(row, columns, blank_none=False)
        record = {column.name: value for column, value in zip(columns, values, strict=True)}
        yield ("" if first else ",") + json.dumps(record, default=str, ensure_ascii=False)
        first = False
    yield "]"


def xlsx_bytes(rows: Iterable[Any], columns: list[Column], *, sheet: str = "Export") -> bytes:
    """A workbook, in one piece because a zip container cannot be streamed.

    `write_only` keeps openpyxl from building a cell object graph for the whole
    sheet, which is what makes the difference between a bounded amount of
    memory and a copy of the table.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Font
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ValidationError(
            "XLSX export is unavailable on this deployment; use CSV or JSON.",
        ) from exc

    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet(title=sheet[:31] or "Export")

    header = []
    for column in columns:
        heading = WriteOnlyCell(worksheet, value=column.title)
        heading.font = Font(bold=True)
        header.append(heading)
    worksheet.append(header)

    for row in rows:
        worksheet.append([defuse(value) for value in _row_values(row, columns)])

    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


# ── the file, for a caller that is not a response ────────────────────────


def write_to(target: BinaryIO, rows: Iterable[Any], columns: list[Column], *, fmt: str) -> int:
    """Write the whole file into `target` and return how many rows it holds.

    The streamed `response` is for a download somebody is waiting on; this is
    for a background export (§30), which has to have the finished bytes before
    it can hand them to object storage. It takes a file object rather than
    returning bytes for the reason the streaming exists at all: a hundred
    thousand rows should cost a buffer, not a copy of the table. Give it a
    `SpooledTemporaryFile` and memory stays bounded whatever the row count.

    XLSX is still assembled in one piece, because a zip container cannot be
    written incrementally — which is why its ceiling is lower.
    """
    counted = 0

    def counting() -> Iterator[Any]:
        nonlocal counted
        for row in rows:
            counted += 1
            yield row

    if fmt == "xlsx":
        target.write(xlsx_bytes(counting(), columns))
        return counted

    lines = json_lines(counting(), columns) if fmt == "json" else csv_lines(counting(), columns)
    for chunk in lines:
        target.write(chunk.encode("utf-8"))
    return counted


# ── the HTTP end ─────────────────────────────────────────────────────────

CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def response(rows: Iterable[Any], columns: list[Column], *, fmt: str, stem: str):
    """The download itself.

    `rows` is expected to be a generator that owns its own database session:
    this returns before a single row has been read, and a session opened by the
    handler would be closed by then. See `stream_rows`.
    """
    from flask import Response

    name = filename(stem, fmt)
    headers = {
        "Content-Disposition": f'attachment; filename="{name}"',
        # Proxies that buffer a streamed response defeat the point of
        # streaming it, and nginx is configured not to for exactly this.
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-store",
    }

    if fmt == "xlsx":
        return Response(xlsx_bytes(rows, columns), mimetype=CONTENT_TYPES[fmt], headers=headers)

    body = json_lines(rows, columns) if fmt == "json" else csv_lines(rows, columns)
    return Response(body, mimetype=CONTENT_TYPES[fmt], headers=headers)


def refuse_if_truncated(statement, *, fmt: str, what: str = "rows") -> int:
    """Count first, and refuse rather than hand back a plausible-looking half.

    `stream_rows` applies a `LIMIT`, which for a long time meant an export of
    200,000 rows produced 50,000 of them with a `200` on it and no indication
    anywhere that the file was a fragment. That is the worst shape a data bug
    can take: quiet, plausible, and impossible for the person holding the file
    to notice. The comment on `MAX_ROWS` had said since it was written that
    such an export "must become a background job" — this is what makes that
    true instead of aspirational.

    A count is one extra query against the same statement, which is cheap
    beside the export it guards. Returns the count so a caller can report it.
    """
    from client.db import session_scope
    from client.errors import ValidationError
    from client.query import count_of

    ceiling = limit_for(fmt)
    with session_scope() as session:
        total = count_of(session, statement)

    if total > ceiling:
        raise ValidationError(
            f"That is {total:,} {what}, and a download stops at {ceiling:,}. "
            "Queue it as an export instead and the whole set is produced in the "
            "background.",
            details={
                "total": total,
                "maximum": ceiling,
                "format": fmt,
                # So a page can offer the queued path without guessing.
                "queue_instead": True,
            },
        )
    return total


def stream_rows(statement, *, limit: int, session: Any = None) -> Iterator[Any]:
    """Rows from a statement, in batches, on a session of the generator's own.

    The session is opened here rather than by the caller because the response
    is returned before the first row is read: a `session_scope()` in the
    handler would already have closed by the time this ran, and the export
    would fail after the headers had gone out — a truncated download with a
    200 on it.

    `session` is for the caller who is *not* a response: `write_to` consumes
    every row before it returns, so a background export (§30) and the seed pass
    that produces the demo artefacts both have a live session to read on. It is
    not an optimisation — it is a correctness fix. A separate session reads a
    separate transaction, so the seed produced an export of *zero* rows over a
    table whose fifty rows were sitting uncommitted in the session it had been
    handed, and recorded that as a finished export of fifty units.
    """
    from client.db import session_scope

    # `nullcontext` when a session is supplied: the caller's transaction is the
    # one to read in, and closing it here would be closing somebody else's.
    scope = contextlib.nullcontext(session) if session is not None else session_scope()
    with scope as session:
        # `partitions` rather than `yield_per`: both keep memory bounded, but
        # `yield_per` holds a *server-side cursor* open across the whole
        # response, and this generator is consumed by the WSGI server after the
        # view has returned. Something in that path was closing the result
        # early: an audit export of 1042 rows wrote 1001 of them one run and
        # 1008 the next, with a 200 on it — the truncated download this
        # function's docstring exists to prevent, arriving by a route nobody
        # had thought of. `partitions` fetches a chunk, materialises it, and
        # only then hands the rows over, so an interrupted response loses the
        # chunk it was in rather than everything after the first.
        result = session.scalars(statement.limit(limit)).unique()
        count = 0
        for chunk in result.partitions(BATCH):
            for row in chunk:
                yield row
                count += 1
                if count >= limit:
                    return
