"""
The tables behind the client app.

One analysed video is one `video_records` row plus its children: the entities
the model extracted, the persons face matching identified, and one row per AI
call. The whole record is kept in `document` as JSONB as well — the flattened
columns are what the explorer filters and charts on, the document is what the
detail view shows, and keeping both means a question nobody anticipated can
still be answered without re-running the video.

    video_records ──┬── record_entities   (type, value)
                    ├── record_persons    (person id)
                    └── record_calls      (one per AI service call)

    saved_searches   a search somebody named, so it can be re-run

`id` is the pipeline's own message id (`vid-demo-1`), not a surrogate key: it is
what the two aggregators group by, what the Kafka messages carry and what the
log lines print, so a row and a log line can be lined up by eye. A re-submitted
video replaces its row — see `store.save_record`.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class VideoRecord(Base):
    """One analysed video — the flattened form of W7's record."""

    __tablename__ = "video_records"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)

    # ---- identity -------------------------------------------------------
    name: Mapped[str] = mapped_column(String(512), default="", index=True)
    path: Mapped[str] = mapped_column(String(1024), default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: submitted -> analysed, in seconds. What "how long did this video take?"
    #: means to whoever submitted it: wall clock, including the queue.
    processing_seconds: Mapped[float | None] = mapped_column(Float)

    # ---- outcome --------------------------------------------------------
    #: `analysed` when every service answered, `partial` when at least one did
    #: not. A record is written either way (AI_FAIL_FAST=false), and a table
    #: that does not say which is which invites reading a half-answer as a
    #: whole one.
    status: Mapped[str] = mapped_column(String(32), default="analysed", index=True)
    failed_services: Mapped[list] = mapped_column(JSONB, default=list)
    errors: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    # ---- what the AI services produced ----------------------------------
    summary: Mapped[str] = mapped_column(Text, default="")
    sentiment: Mapped[str] = mapped_column(String(32), default="", index=True)
    entities_text: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    transcript_format: Mapped[str] = mapped_column(String(32), default="")
    ocr_text: Mapped[str] = mapped_column(Text, default="")

    persons: Mapped[list] = mapped_column(JSONB, default=list)
    person_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_frames_count: Mapped[int] = mapped_column(Integer, default=0)

    #: Character counts, so "the videos with no speech" is a filter rather than
    #: a scan of every transcript.
    summary_chars: Mapped[int] = mapped_column(Integer, default=0)
    transcript_chars: Mapped[int] = mapped_column(Integer, default=0)
    description_chars: Mapped[int] = mapped_column(Integer, default=0)
    ocr_chars: Mapped[int] = mapped_column(Integer, default=0)

    #: Which model answered the summary prompt, and the prompt's hash — two
    #: records summarised by different models are not comparable, and the hash
    #: is how you tell that the prompt changed underneath a corpus.
    model: Mapped[str] = mapped_column(String(128), default="", index=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")

    #: Was any answer in this record mocked? A dashboard that mixes mocked runs
    #: into its averages is reporting on `src/mock/mock_responses.py`.
    mocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    #: Everything at once, for the free-text `q` sweep: summary + entities +
    #: transcript + description + OCR. One ILIKE instead of five.
    search_text: Mapped[str] = mapped_column(Text, default="")

    #: W7's complete record, verbatim — the detail view, and the answer to a
    #: question these columns did not anticipate.
    document: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    entities: Mapped[list["RecordEntity"]] = relationship(
        back_populates="record", cascade="all, delete-orphan", lazy="selectin"
    )
    people: Mapped[list["RecordPerson"]] = relationship(
        back_populates="record", cascade="all, delete-orphan", lazy="selectin"
    )
    calls: Mapped[list["RecordCall"]] = relationship(
        back_populates="record", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_video_records_analysed_status", "analysed_at", "status"),
    )


class RecordEntity(Base):
    """One `TYPE: value` line of the entities answer, parsed.

    The raw line is kept next to the split parts: the prompt asks for
    `LOCATION: Ceuta`, models sometimes answer `Ceuta`, and a row that dropped
    the original would make that indistinguishable from a parse bug.
    """

    __tablename__ = "record_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("video_records.id", ondelete="CASCADE"), index=True
    )
    #: NAME / LOCATION / DATE / … — uppercased, or `UNTYPED` when the model
    #: answered a bare value.
    type: Mapped[str] = mapped_column(String(64), default="UNTYPED", index=True)
    value: Mapped[str] = mapped_column(String(512), default="")
    #: Case-folded, so "Ceuta" and "ceuta" are one entity in a top-10.
    value_key: Mapped[str] = mapped_column(String(512), default="", index=True)
    raw: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    record: Mapped[VideoRecord] = relationship(back_populates="entities")

    __table_args__ = (Index("ix_record_entities_type_value", "type", "value_key"),)


class RecordPerson(Base):
    """One person id that face matching (:8821) put in this video."""

    __tablename__ = "record_persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("video_records.id", ondelete="CASCADE"), index=True
    )
    person: Mapped[str] = mapped_column(String(128), default="", index=True)

    record: Mapped[VideoRecord] = relationship(back_populates="people")


class RecordCall(Base):
    """One call to one AI service, as it happened for this video.

    This is the provenance the record itself deliberately leaves out (mocked or
    live, which URL, how long) — it travels on the branch messages, and W7
    hands it here so the statistics page can be built from something other than
    log lines.
    """

    __tablename__ = "record_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("video_records.id", ondelete="CASCADE"), index=True
    )
    #: `face-match-main`, `video-describe-354b`, `video-ocr`, `transcribe`,
    #: `summary`, `entities`, `sentiment` — W6's three prompts are three calls.
    service: Mapped[str] = mapped_column(String(64), default="", index=True)
    mocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(512), default="")
    duration_ms: Mapped[float | None] = mapped_column(Float)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    error: Mapped[str] = mapped_column(Text, default="")

    #: From the service's own metadata, when it reports them.
    model: Mapped[str] = mapped_column(String(128), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    service_seconds: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    analysed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    record: Mapped[VideoRecord] = relationship(back_populates="calls")


class SavedSearch(Base):
    """A question somebody named, so it can be asked again.

    The payload is the explorer's own request body — filters, free text, the
    condition tree, the columns and the sort. Storing the request rather than a
    rendered SQL string is what lets a saved search survive a new filter being
    added to the resource.
    """

    __tablename__ = "saved_searches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    #: No auth yet, so this is a label rather than a principal (see the compose
    #: notes): whoever typed it, for a shared PoC instance.
    owner: Mapped[str] = mapped_column(String(128), default="", index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Prompt(Base):
    """One of the three prompts W6 posts to :8825, as edited in the UI.

    The `.txt` files under `src/prompts/` remain the **default** — what a fresh
    database starts from and what the app falls back to when PostgreSQL is not
    there. A row here overrides its file, so the wording can be changed by an
    analyst at 11pm without a deploy, and the change is visible to every worker
    in the process on the next call.

    `version` increments on every save and rides along in the record's
    metadata, which is what makes "why did last week's summaries read
    differently?" answerable after the fact.
    """

    __tablename__ = "prompts"

    #: `summary` | `entities` | `sentiment` — the call it belongs to, not the
    #: file name: the file is where the default lives, this is what it is for.
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text, default="")
    #: What the file said when this row was first created, so "reset to the
    #: shipped wording" does not need the file to still be there.
    default_text: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = [
    "Base",
    "VideoRecord",
    "RecordEntity",
    "RecordPerson",
    "RecordCall",
    "SavedSearch",
    "Prompt",
    "func",
]
