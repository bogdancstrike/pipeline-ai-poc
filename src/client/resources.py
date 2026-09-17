"""
What the client may ask about a video record.

One declaration, three consumers: the filter bar (`?sentiment=NEGATIVE`), the
advanced query builder (which is *generated* from `FIELDS.describe()`), and the
export. Declaring the columns once is what stops the builder offering an
operator the SQL layer cannot honour, and stops a filter being case-sensitive
on one screen and not on another.

Fields whose kind is `enum` carry their choices, so the builder can render a
select without a round trip; `facet=True` asks for a GROUP BY count so the menu
is built from the data rather than a hardcoded list that drifts from it.
"""

from client.models import RecordEntity, RecordPerson, VideoRecord
from client.query import Field, FieldSet

#: The sentiment prompt is asked for one of these three words, in capitals.
#: Anything else a model returns still stores and still shows — the choices are
#: what the builder offers, not what the column accepts.
SENTIMENTS = ("POSITIVE", "NEUTRAL", "NEGATIVE")

STATUSES = ("analysed", "partial")

#: Every AI call a record can account for, as `record_calls.service` spells it.
SERVICES = (
    "face-match-main",
    "video-describe-354b",
    "transcribe",
    "video-ocr",
    "summary",
    "entities",
    "sentiment",
)

FIELDS = FieldSet(
    Field("id", VideoRecord.id, kind="text", label="Record id", searchable=True),
    Field("name", VideoRecord.name, kind="text", label="Video", searchable=True),
    Field("path", VideoRecord.path, kind="text", label="Path", searchable=True),
    Field(
        "status",
        VideoRecord.status,
        kind="enum",
        label="Status",
        facet=True,
        choices=STATUSES,
    ),
    Field(
        "sentiment",
        VideoRecord.sentiment,
        kind="enum",
        label="Sentiment",
        facet=True,
        choices=SENTIMENTS,
    ),
    Field("summary", VideoRecord.summary, kind="text", label="Summary", searchable=True),
    Field(
        "entities_text",
        VideoRecord.entities_text,
        kind="text",
        label="Entities",
        searchable=True,
    ),
    Field(
        "transcript",
        VideoRecord.transcript,
        kind="text",
        label="Transcript",
        searchable=True,
    ),
    Field(
        "description",
        VideoRecord.description,
        kind="text",
        label="Description",
        searchable=True,
    ),
    Field("ocr_text", VideoRecord.ocr_text, kind="text", label="On-screen text", searchable=True),
    Field("model", VideoRecord.model, kind="enum", label="Model", facet=True),
    Field("prompt_hash", VideoRecord.prompt_hash, kind="text", label="Prompt hash"),
    Field("mocked", VideoRecord.mocked, kind="bool", label="Mocked run", facet=True),
    Field("persons", VideoRecord.persons, kind="json", label="Persons", searchable=True),
    Field("person_count", VideoRecord.person_count, kind="number", label="Persons"),
    Field("entity_count", VideoRecord.entity_count, kind="number", label="Entities"),
    Field("ocr_frames_count", VideoRecord.ocr_frames_count, kind="number", label="OCR frames"),
    Field("transcript_chars", VideoRecord.transcript_chars, kind="number", label="Transcript size"),
    Field("summary_chars", VideoRecord.summary_chars, kind="number", label="Summary size"),
    Field("error_count", VideoRecord.error_count, kind="number", label="Failed services"),
    Field(
        "processing_seconds",
        VideoRecord.processing_seconds,
        kind="number",
        label="Processing time (s)",
    ),
    Field("analysed_at", VideoRecord.analysed_at, kind="datetime", label="Analysed"),
    Field("submitted_at", VideoRecord.submitted_at, kind="datetime", label="Submitted"),
    # The free-text sweep every `q=` runs over. Not offered as a column in the
    # table: it is the other five texts concatenated, and showing it would be
    # showing the same words a second time.
    Field(
        "search_text",
        VideoRecord.search_text,
        kind="text",
        label="Any text",
        searchable=True,
        sortable=False,
    ),
)

#: The columns the explorer table shows until somebody picks others.
DEFAULT_COLUMNS = (
    "name",
    "analysed_at",
    "sentiment",
    "person_count",
    "entity_count",
    "status",
    "processing_seconds",
)

#: Columns an export carries when none are named — wider than the table, because
#: a spreadsheet is read away from the app that could have shown the rest.
EXPORT_COLUMNS = DEFAULT_COLUMNS + ("id", "path", "model", "mocked", "summary")

DEFAULT_SORT = "analysed_at"

#: The entity list has its own small field set, for the entities browser.
ENTITY_FIELDS = FieldSet(
    Field("type", RecordEntity.type, kind="enum", label="Type", facet=True),
    Field("value", RecordEntity.value, kind="text", label="Value", searchable=True),
    Field("record_id", RecordEntity.record_id, kind="text", label="Record"),
)

PERSON_FIELDS = FieldSet(
    Field("person", RecordPerson.person, kind="text", label="Person", searchable=True),
    Field("record_id", RecordPerson.record_id, kind="text", label="Record"),
)
