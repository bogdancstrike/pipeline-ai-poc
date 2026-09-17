"""
`record_writer` and `publisher` — where a finished record goes, and how a
video gets submitted in the first place.

The file sink is the pipeline's product: it is written before the database row
and it is what survives a database outage, so its atomicity and its naming are
worth pinning.
"""

import json
import os

import pytest

import publisher
import record_writer
from config import Config, Topics


@pytest.fixture()
def output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "OUTPUT_WRITE_FILE", True)
    return tmp_path


RECORD = {
    "id": "vid-1",
    "name": "migrants.mp4",
    "path": "/video/migrants.mp4",
    "enrichment": {"summary": {"text": "something happened"}},
    "errors": {},
}


# ── where the record lands ───────────────────────────────────────────────


def test_the_file_is_named_after_the_video_without_its_extension(output_dir):
    assert record_writer.output_path("migrants.mp4").endswith("migrants_analysis.json")


def test_a_path_is_reduced_to_its_file_name(output_dir):
    assert os.path.basename(
        record_writer.output_path("/video/Inmigracion/1abe.mp4")
    ) == "1abe_analysis.json"


def test_a_nameless_video_still_produces_a_file(output_dir):
    assert os.path.basename(record_writer.output_path("")) == "video_analysis.json"


def test_unique_names_append_the_run_id_so_a_rerun_keeps_both(output_dir, monkeypatch):
    monkeypatch.setenv("OUTPUT_UNIQUE_NAMES", "true")
    path = record_writer.output_path("migrants.mp4", "vid-7")
    assert path.endswith("migrants-vid-7_analysis.json")


def test_without_unique_names_a_rerun_replaces_the_file(output_dir, monkeypatch):
    monkeypatch.setenv("OUTPUT_UNIQUE_NAMES", "false")
    first = record_writer.output_path("migrants.mp4", "vid-7")
    second = record_writer.output_path("migrants.mp4", "vid-8")
    assert first == second


# ── writing it ───────────────────────────────────────────────────────────


def test_the_record_is_written_as_readable_json(output_dir):
    path = record_writer.write(RECORD)

    written = json.loads(open(path, encoding="utf-8").read())
    assert written == RECORD


def test_the_file_ends_with_a_newline(output_dir):
    path = record_writer.write(RECORD)
    assert open(path, encoding="utf-8").read().endswith("\n")


def test_accents_survive_the_round_trip(output_dir):
    record = dict(RECORD, name="málaga.mp4", enrichment={"summary": {"text": "Ceuta and Melilla"}})
    path = record_writer.write(record)
    assert "málaga" in open(path, encoding="utf-8").read()


def test_no_half_written_file_is_left_behind(output_dir):
    """Written beside the target and renamed, so a reader never sees half."""
    record_writer.write(RECORD)
    assert [p.name for p in output_dir.glob("*.tmp")] == []


def test_the_directory_is_created_when_it_is_missing(tmp_path, monkeypatch):
    nested = tmp_path / "does" / "not" / "exist"
    monkeypatch.setattr(Config, "OUTPUT_DIR", str(nested))
    monkeypatch.setattr(Config, "OUTPUT_WRITE_FILE", True)

    assert os.path.isfile(record_writer.write(RECORD))


def test_writing_can_be_turned_off(output_dir, monkeypatch):
    monkeypatch.setattr(Config, "OUTPUT_WRITE_FILE", False)
    assert record_writer.write(RECORD) is None
    assert list(output_dir.iterdir()) == []


# ── submitting a video ───────────────────────────────────────────────────


@pytest.fixture()
def broker(monkeypatch):
    """A producer that records what was sent instead of opening a socket."""
    sent = []

    class Future:
        def get(self, timeout=None):
            return {"partition": 0, "offset": 1}

    class Producer:
        def send(self, topic, value=None, key=None):
            sent.append({"topic": topic, "value": value, "key": key})
            return Future()

    monkeypatch.setattr(publisher, "get_producer", lambda: Producer())
    return sent


def test_a_submission_lands_on_the_video_in_topic(broker):
    publisher.publish_video(path="/video/migrants.mp4", video_id="vid-1")

    assert broker[0]["topic"] == Topics.VIDEO_IN
    assert broker[0]["value"]["path"] == "/video/migrants.mp4"


def test_the_message_is_keyed_by_the_run_id(broker):
    """Both aggregators regroup on it; the key is what keeps a run on one partition."""
    publisher.publish_video(path="/video/migrants.mp4", video_id="vid-1")
    assert broker[0]["key"] == "vid-1"


def test_the_run_is_named_after_the_video_file_by_default(broker):
    answer = publisher.publish_video(path="/video/Inmigracion/1abe85d1.mp4")

    assert answer["id"] == "1abe85d1.mp4"


def test_re_submitting_the_same_file_is_the_same_run(broker):
    """Which is what makes a re-analysis replace its record rather than double it."""
    first = publisher.publish_video(path="/video/migrants.mp4")
    second = publisher.publish_video(path="/video/migrants.mp4")
    assert first["id"] == second["id"]


def test_an_explicit_id_keeps_two_answers_apart(broker):
    first = publisher.publish_video(path="/video/migrants.mp4", video_id="run-a")
    second = publisher.publish_video(path="/video/migrants.mp4", video_id="run-b")
    assert first["id"] != second["id"]


def test_a_path_with_no_file_name_falls_back_to_a_generated_id(broker):
    answer = publisher.publish_video(path="/")
    assert answer["id"].startswith("vid-")


def test_the_submission_carries_the_moment_it_was_made(broker):
    publisher.publish_video(path="/video/x.mp4")
    assert broker[0]["value"]["submitted_at"]


def test_transcribe_overrides_ride_along(broker):
    publisher.publish_video(path="/video/x.mp4", options={"language": "es"})
    assert broker[0]["value"]["options"] == {"language": "es"}


def test_no_options_key_is_sent_when_there_are_none(broker):
    publisher.publish_video(path="/video/x.mp4")
    assert "options" not in broker[0]["value"]


def test_the_answer_names_the_file_the_record_will_be_written_to(broker, output_dir):
    answer = publisher.publish_video(path="/video/migrants.mp4", name="migrants.mp4")
    assert answer["output_file"].endswith("migrants_analysis.json")
