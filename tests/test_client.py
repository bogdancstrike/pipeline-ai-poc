"""
The client app: W7's record becomes rows, and the rows answer questions.

These run against **SQLite in memory**, not PostgreSQL. The trade is deliberate
and its edges are stated here rather than discovered later:

  * what it does cover — the record -> row mapping, the filter/operator engine,
    the condition-tree compiler, the serialisation the UI reads, saved searches
    and the export. That is where the logic is.
  * what it cannot cover — `date_trunc`, `percentile_cont` and JSONB operators,
    which SQLite has no equivalent for. The dashboard and statistics queries
    are therefore exercised by hand against a real PostgreSQL (see the README)
    and are skipped here rather than faked into passing.

`JSONB` is bound to SQLite's `JSON` for the duration, which is the only place
the schema is bent to fit the test.
"""

import pytest

pytest.importorskip("sqlalchemy", reason="the client app needs SQLAlchemy")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from config import Config  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):  # pragma: no cover - a dialect shim
    return "JSON"


@pytest.fixture()
def db(monkeypatch):
    """A schema-ready in-memory database, wired into `client.db`."""
    from client import db as client_db
    from client import models

    engine = create_engine(
        "sqlite+pysqlite:///:memory:", poolclass=StaticPool, future=True
    )
    monkeypatch.setattr(Config, "DB_ENABLED", True)
    monkeypatch.setattr(client_db, "_engine", engine)
    monkeypatch.setattr(client_db, "_maker", sessionmaker(bind=engine, expire_on_commit=False, future=True))
    monkeypatch.setattr(client_db, "_schema_ready", True)
    models.Base.metadata.create_all(engine)
    return client_db


@pytest.fixture()
def record():
    """A finished W7 record — one video, every service having answered."""
    return {
        "id": "vid-1",
        "name": "migrants.mp4",
        "path": "/video/migrants.mp4",
        "submitted_at": "2026-09-17T07:30:00+00:00",
        "analysed_at": "2026-09-17T07:30:27+00:00",
        "enrichment": {
            "face_match": {"persons": ["222", "409"], "message": "ok"},
            "description": {"text": "Migrants on a shoreline", "metadata": {}},
            "transcript": {"text": "00: Hello.", "format": "dialog", "metadata": {}},
            "ocr": {"text": "Reaction", "frames_count": 9, "metadata": {}},
            "summary": {
                "text": "Migrants crossing into Ceuta.",
                "prompt": "summary.txt",
                "metadata": {"model": "phi4:14b-q8_0", "prompt_hash": "34f899", "duration_seconds": 7.3},
            },
            "entities": {
                "list": ["LOCATION: Ceuta", "NAME: Red Cross"],
                "text": "LOCATION: Ceuta\nNAME: Red Cross",
                "metadata": {},
            },
            "sentiment": {"text": "negative", "metadata": {}},
        },
        "errors": {},
    }


@pytest.fixture()
def calls():
    """W6's provenance, which the record itself leaves out."""
    return {
        "face-match-main": {"mocked": False, "endpoint": "http://ai:8821/match", "duration_ms": 1843.2},
        "summary": {"mocked": False, "endpoint": "http://ai:8825/summarize", "duration_ms": 7307.0},
    }


# ----------------------------------------------------------------- store --

def test_a_record_becomes_one_row_and_its_children(db, record, calls):
    from client import models, store

    assert store.save_record(record, calls) == "vid-1"

    with db.session_scope() as session:
        row = session.get(models.VideoRecord, "vid-1")
        assert row.status == "analysed"
        # The prompt answers in whatever case it likes; the column is one case,
        # so a chart has one bucket per sentiment rather than three.
        assert row.sentiment == "NEGATIVE"
        assert row.persons == ["222", "409"]
        assert row.person_count == 2
        assert row.entity_count == 2
        assert row.processing_seconds == 27.0
        assert row.model == "phi4:14b-q8_0"
        # Every text at once, so `q=` is one ILIKE instead of five.
        assert "Ceuta" in row.search_text and "Hello" in row.search_text
        # The record, verbatim — the detail view and the file on disk agree.
        assert row.document["enrichment"]["summary"]["prompt"] == "summary.txt"


def test_entities_are_split_into_type_and_value(db, record):
    from client import models, store

    record["enrichment"]["entities"]["list"] = ["LOCATION: Ceuta", "Red Cross", "date: 1 August"]
    store.save_record(record)

    with db.session_scope() as session:
        row = session.get(models.VideoRecord, "vid-1")
        parsed = sorted((e.type, e.value) for e in row.entities)
    # A bare value keeps UNTYPED rather than being dropped, and the type is
    # normalised so `date:` and `DATE:` are one bucket.
    assert parsed == [("DATE", "1 August"), ("LOCATION", "Ceuta"), ("UNTYPED", "Red Cross")]


def test_a_failed_service_makes_the_record_partial(db, record):
    from client import models, store

    record["errors"] = {"video-ocr": "video-ocr at http://ai:8823/ocr failed after 3 attempts"}
    store.save_record(record)

    with db.session_scope() as session:
        row = session.get(models.VideoRecord, "vid-1")
        assert row.status == "partial"
        assert row.failed_services == ["video-ocr"]
        # The failed call is a row too: absent from the statistics would be
        # the one thing worse than slow.
        failed = [call for call in row.calls if not call.ok]
        assert [call.service for call in failed] == ["video-ocr"]


def test_re_analysing_a_video_replaces_its_row(db, record, calls):
    from client import models, store

    store.save_record(record, calls)
    record["enrichment"]["summary"]["text"] = "A second opinion."
    record["enrichment"]["entities"]["list"] = ["LOCATION: Ceuta"]
    store.save_record(record, calls)

    with db.session_scope() as session:
        rows = session.query(models.VideoRecord).all()
        assert len(rows) == 1
        assert rows[0].summary == "A second opinion."
        # The children are replaced wholesale — a re-analysis is a new answer,
        # not an edit of the old one.
        assert len(rows[0].entities) == 1


def test_a_dead_database_costs_the_row_not_the_record(record, monkeypatch):
    """W7 must not raise because PostgreSQL is down: the record is already on disk."""
    from client import db as client_db
    from client import store

    monkeypatch.setattr(Config, "DB_ENABLED", True)
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql+psycopg2://nobody@127.0.0.1:1/none")
    monkeypatch.setattr(client_db, "_engine", None)
    monkeypatch.setattr(client_db, "_maker", None)
    monkeypatch.setattr(client_db, "_schema_ready", False)
    monkeypatch.setattr(client_db, "create_schema", lambda: None)

    assert store.save_record(record) is None


# -------------------------------------------------------------- explorer --

def test_free_text_sweeps_every_searchable_field(db, record):
    from client import explorer, store

    store.save_record(record)
    with db.session_scope() as session:
        # A word that appears only in the transcript still finds the record.
        assert explorer.search(session, {"query_text": "hello"})["total"] == 1
        assert explorer.search(session, {"query_text": "ceuta"})["total"] == 1
        assert explorer.search(session, {"query_text": "nothing here"})["total"] == 0


def test_filters_and_operators_narrow_in_sql(db, record):
    from client import explorer, store

    store.save_record(record)
    with db.session_scope() as session:
        assert explorer.search(session, {"filters": {"sentiment": "NEGATIVE"}})["total"] == 1
        assert explorer.search(session, {"filters": {"sentiment": "POSITIVE"}})["total"] == 0
        assert explorer.search(session, {"filters": {"person_count__gt": 1}})["total"] == 1
        assert explorer.search(session, {"filters": {"person_count__gt": 5}})["total"] == 0
        assert explorer.search(session, {"filters": {"name__starts": "migr"}})["total"] == 1
        assert explorer.search(session, {"filters": {"prompt_hash__empty": "true"}})["total"] == 0


def test_the_condition_tree_compiles_and_reads_back(db, record):
    from client import explorer, store

    store.save_record(record)
    tree = {
        "type": "group",
        "conjunction": "AND",
        "children1": {
            "a": {"type": "rule", "properties": {
                "field": "sentiment", "operator": "select_equals", "value": ["NEGATIVE"]}},
            "b": {"type": "rule", "properties": {
                "field": "person_count", "operator": "greater", "value": [0]}},
        },
    }
    with db.session_scope() as session:
        page = explorer.search(session, {"condition_tree": tree})

    assert page["total"] == 1
    assert page["rule_count"] == 2
    # The inspector text is produced by walking the same tree that compiled to
    # SQL, so what a reader checks is provably what ran.
    assert "Sentiment" in page["condition_text"] and "Persons" in page["condition_text"]


def test_a_half_typed_rule_does_not_blank_the_results(db, record):
    """The editor sends the tree on every keystroke; an unfinished rule is skipped."""
    from client import explorer, store

    store.save_record(record)
    tree = {
        "type": "group",
        "conjunction": "AND",
        "children1": {"a": {"type": "rule", "properties": {"field": "sentiment", "operator": "select_equals"}}},
    }
    with db.session_scope() as session:
        assert explorer.search(session, {"condition_tree": tree})["total"] == 1


def test_an_unknown_field_is_refused_by_name(db):
    from client.errors import ValidationError
    from client import explorer

    tree = {"type": "group", "children1": {
        "a": {"type": "rule", "properties": {"field": "nope", "operator": "equal", "value": ["x"]}}}}
    with db.session_scope() as session:
        with pytest.raises(ValidationError):
            explorer.search(session, {"condition_tree": tree})


def test_facets_are_counted_from_the_data(db, record):
    from client import explorer, store

    store.save_record(record)
    with db.session_scope() as session:
        page = explorer.search(session, {"facets": True})

    sentiments = {str(item["value"]): item["count"] for item in page["facets"]["sentiment"]}
    assert sentiments == {"NEGATIVE": 1}


def test_the_detail_carries_every_branch_and_the_document(db, record, calls):
    from client import explorer, store

    store.save_record(record, calls)
    with db.session_scope() as session:
        detail = explorer.detail(session, "vid-1")

    assert detail["summary"].startswith("Migrants crossing")
    assert detail["transcript"] == "00: Hello."
    assert detail["persons"] == ["222", "409"]
    assert [entity["type"] for entity in detail["entities"]] == ["LOCATION", "NAME"]
    assert detail["document"]["id"] == "vid-1"
    by_service = {call["service"]: call for call in detail["calls"]}
    assert by_service["face-match-main"]["duration_ms"] == 1843.2


def test_a_missing_record_is_a_404_not_an_empty_body(db):
    from client.errors import NotFoundError
    from client import explorer

    with db.session_scope() as session:
        with pytest.raises(NotFoundError):
            explorer.detail(session, "no-such-video")


def test_related_records_share_an_entity(db, record):
    from client import explorer, store

    store.save_record(record)
    second = dict(record, id="vid-2", name="second.mp4")
    second["enrichment"] = dict(record["enrichment"])
    second["enrichment"]["entities"] = {"list": ["LOCATION: Ceuta"], "text": "LOCATION: Ceuta", "metadata": {}}
    store.save_record(second)

    with db.session_scope() as session:
        related = explorer.neighbours(session, "vid-1")

    assert [item["id"] for item in related["items"]] == ["vid-2"]
    assert related["items"][0]["shared"] == ["Ceuta"]


def test_the_export_carries_the_same_question(db, record):
    from client import explorer, store
    from client.export import csv_lines

    store.save_record(record)
    with db.session_scope() as session:
        statement = explorer.export_statement({"filters": {"sentiment": "NEGATIVE"}})
        rows = session.scalars(statement).unique().all()
        columns = explorer.export_columns(["name", "sentiment", "entity_count"])
        text = "".join(csv_lines(rows, columns))

    lines = text.strip().splitlines()
    assert lines[0] == "Video,Sentiment,Entities"
    assert lines[1].startswith("migrants.mp4,NEGATIVE,2")


# --------------------------------------------------------- saved searches --

def test_a_saved_search_stores_the_question_not_the_answer(db, record):
    from client import explorer, saved_searches, store

    store.save_record(record)
    with db.session_scope() as session:
        saved = saved_searches.create(session, {
            "name": "Negative, with people",
            "owner": "ana",
            "payload": {"filters": {"sentiment": "NEGATIVE"}, "query_text": "", "page_size": 50},
        })
        assert saved["payload"]["filters"] == {"sentiment": "NEGATIVE"}

        # Running it asks the question again, of whatever is in the table now.
        stored = saved_searches.resolve(session, saved["id"])
        assert explorer.search(session, stored)["total"] == 1

        saved_searches.mark_run(session, saved["id"])
        listing = saved_searches.listing(session, {})
        assert listing["total"] == 1
        assert listing["items"][0]["run_count"] == 1


def test_a_saved_search_needs_a_name(db):
    from client.errors import ValidationError
    from client import saved_searches

    with db.session_scope() as session:
        with pytest.raises(ValidationError):
            saved_searches.create(session, {"payload": {}})


# ------------------------------------------------------------------ prompts --

def test_the_prompt_files_seed_the_database_once(db):
    """The .txt files are the default; a row is created from each, once."""
    from client import models, prompt_store

    with db.session_scope() as session:
        assert prompt_store.seed(session) == 3
    with db.session_scope() as session:
        # Seeding again must not overwrite: a default does not undo an edit.
        assert prompt_store.seed(session) == 0
        rows = session.query(models.Prompt).all()

    assert sorted(row.name for row in rows) == ["entities", "sentiment", "summary"]
    assert all(row.text == row.default_text for row in rows)


def test_an_edited_prompt_is_what_the_worker_sends(db, monkeypatch):
    """`prompts.load()` prefers the stored copy — that is the whole feature."""
    import prompts
    from client import prompt_store

    monkeypatch.setattr(Config, "PROMPTS_FROM_DB", True)
    shipped = prompts.from_file("summary.txt")
    prompt_store.invalidate()

    with db.session_scope() as session:
        prompt_store.seed(session)
        prompt_store.save(session, "summary", "Summarise in one sentence.", updated_by="ana")

    assert prompts.load("summary.txt") == "Summarise in one sentence."
    # The file is untouched, and still reachable for the reset.
    assert prompts.from_file("summary.txt") == shipped

    with db.session_scope() as session:
        prompt_store.reset(session, "summary")
    assert prompts.load("summary.txt") == shipped


def test_a_saved_prompt_takes_effect_without_a_restart(db, monkeypatch):
    """Saving drops this process's cache, so the next call reads the new text."""
    import prompts
    from client import prompt_store

    monkeypatch.setattr(Config, "PROMPTS_FROM_DB", True)
    with db.session_scope() as session:
        prompt_store.seed(session)

    prompts.load("entities.txt")  # warm the cache
    with db.session_scope() as session:
        prompt_store.save(session, "entities", "One entity per line.")
    assert prompts.load("entities.txt") == "One entity per line."


def test_prompt_edits_are_versioned_and_validated(db):
    from client.errors import NotFoundError, ValidationError
    from client import prompt_store

    with db.session_scope() as session:
        prompt_store.seed(session)
        first = prompt_store.save(session, "sentiment", "One word.")
        again = prompt_store.save(session, "sentiment", "One word.")
        changed = prompt_store.save(session, "sentiment", "One word, in capitals.")

    # An unchanged save does not burn a version; a changed one does.
    assert (first["version"], again["version"], changed["version"]) == (2, 2, 3)

    with db.session_scope() as session:
        with pytest.raises(ValidationError):
            prompt_store.save(session, "summary", "   ")
        with pytest.raises(NotFoundError):
            prompt_store.save(session, "not-a-prompt", "x")


def test_the_pipeline_survives_the_prompt_database_being_down(monkeypatch):
    """A prompt outage must cost the edits, never the video."""
    import prompts
    from client import prompt_store

    monkeypatch.setattr(Config, "DB_ENABLED", False)
    prompt_store.invalidate()
    assert prompts.load("summary.txt") == prompts.from_file("summary.txt")


# -------------------------------------------------------------------- media --

def test_a_video_is_found_by_the_tail_of_its_path(tmp_path, monkeypatch):
    """The AI host's root and ours differ; the file name alone is not enough."""
    from client import media

    mounted = tmp_path / "videos"
    (mounted / "Inmigracion").mkdir(parents=True)
    video = mounted / "Inmigracion" / "1abe85d1.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(mounted)])

    # What the record holds is the AI host's path.
    assert media.locate("/video/Inmigracion/1abe85d1.mp4") == str(video)
    # And the local path itself still works.
    assert media.locate(str(video)) == str(video)
    assert media.locate("/video/Inmigracion/missing.mp4") is None


def test_only_videos_inside_a_search_dir_are_served(tmp_path, monkeypatch):
    from client import media

    mounted = tmp_path / "videos"
    mounted.mkdir()
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"x")
    (mounted / "notes.txt").write_text("not a video")
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(mounted)])

    # Absolute path outside the mount: refused even though the file exists.
    assert media.locate(str(outside)) is None
    # A symlink that leads out of the mount: refused after realpath.
    link = mounted / "escape.mp4"
    link.symlink_to(outside)
    assert media.locate(str(link)) is None
    # Not a video extension: refused.
    assert media.locate(str(mounted / "notes.txt")) is None


def test_a_sibling_directory_is_not_inside_the_mount(tmp_path, monkeypatch):
    """`/app/videos-secret` starts with `/app/videos` as a string only."""
    from client import media

    mounted = tmp_path / "videos"
    mounted.mkdir()
    sibling = tmp_path / "videos-secret"
    sibling.mkdir()
    hidden = sibling / "x.mp4"
    hidden.write_bytes(b"x")
    monkeypatch.setattr(Config, "VIDEO_SEARCH_DIRS", [str(mounted)])

    assert media.locate(str(hidden)) is None
