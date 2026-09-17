"""
End-to-end integration test — the whole pipeline through real infrastructure.

Publishes one video to `video.in` and waits for the terminal `video.done` event,
exercising the splitter's 4-way fan-out, the four extraction workers, the
framework's Redis-backed aggregation in W6 (3 content branches) and in W7 (the
face branch + W6), and the record W7 writes.

Every worker runs mocked (conftest.py sets MOCK_WORKER_*=True), so this needs
Kafka + Redis but NOT the AI host — which is the point: the mock switches make
the full topology testable without 172.17.12.80.

Requires `docker compose up -d kafka redis`. Auto-skips if either is
unreachable, so the unit suite still runs anywhere.
"""

import json
import socket
import time
import uuid

import pytest

from config import Config, Topics

pytestmark = pytest.mark.integration


def _port_open(host: str, port, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _infra_up() -> bool:
    kafka_host, _, kafka_port = Config.KAFKA_BOOTSTRAP_SERVERS.partition(":")
    return _port_open(kafka_host, kafka_port) and _port_open(Config.REDIS_HOST, Config.REDIS_PORT)


@pytest.fixture(scope="module", autouse=True)
def sweep_records():
    """Remove the rows these runs leave in PostgreSQL.

    The messages go to the real broker, so the *running app container* — which
    has the database on — turns each one into a record. They are prefixed `it-`
    and swept here, or they accumulate in whatever corpus somebody is looking
    at on that machine.
    """
    yield

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    try:
        from integration.conftest import sweep
    except Exception:  # pragma: no cover - the helpers are optional
        return

    sweep("it-")


@pytest.fixture(scope="module")
def etl_thread():
    """Start the ETL runtime once for the module and leave it running (daemon)."""
    if not _infra_up():
        pytest.skip("infra (kafka/redis) not reachable — start docker compose")

    from framework.app import FrameworkApp, FrameworkSettings

    settings = FrameworkSettings(
        enable_etl=True,
        enable_api=False,
        enable_dynamic_endpoints=False,
        worker_modules=["workers.pipeline"],
        kafka_bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        consumer_name=Config.WORKER_NAME,
        enable_tracing=False,
    )
    fw = FrameworkApp(settings)
    fw.run()  # starts ETL in a daemon thread
    # Give the consumer time to join the group and get partition assignments.
    time.sleep(8)
    yield fw


def _await_done(video_id: str, timeout_sec: float = 120.0) -> dict:
    """Consume `video.done` until the event for this submission shows up.

    The consumer is created *after* the video is published, and a fully mocked
    pipeline finishes in a few hundred milliseconds — well before a new
    consumer finishes joining. So it reads from `earliest` and filters by id:
    the group id is unique per call, the events are tiny, and replaying the
    topic is the difference between a deterministic test and a coin flip.
    """
    from kafka import KafkaConsumer

    done = KafkaConsumer(
        Topics.DONE,
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        group_id=f"{Config.WORKER_NAME}-it-{uuid.uuid4().hex[:6]}",
        consumer_timeout_ms=1000,
    )
    try:
        # No separate "force assignment" poll: its records would be discarded.
        # The loop below polls until the deadline, which covers the join too.
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            for records in done.poll(timeout_ms=1000).values():
                for record in records:
                    event = json.loads(record.value.decode("utf-8"))
                    if event.get("id") == video_id:
                        return event
    finally:
        done.close()
    return {}


def test_one_video_fans_out_aggregates_twice_and_produces_a_record(etl_thread, tmp_path, monkeypatch):
    import publisher

    monkeypatch.setattr(Config, "OUTPUT_DIR", str(tmp_path))
    video_id = f"it-{uuid.uuid4().hex[:8]}"

    publisher.publish_video(path="/video/migrants.mp4", video_id=video_id, name="migrants.mp4")

    event = _await_done(video_id)
    assert event, f"no video.done event for {video_id} within the timeout"
    assert event["status"] == "analysed"
    assert event["persons"] == 1
    assert event["entities"] == 5
    assert event["sentiment"] == "NEGATIVE"
    assert event["output_file"]


def test_the_same_path_twice_is_one_id_and_an_explicit_id_keeps_both(etl_thread):
    """The run is named after the file, so re-submitting one replaces its record.

    That is the documented contract of `publish_video`: the file name is the
    identifier the submitting systems already use, and both aggregators key on
    it — so two submissions of the same path are deliberately the same run.
    Keeping both answers is what an explicit `video_id` is for.
    """
    import publisher

    first = publisher.publish_video(path="/video/migrants.mp4")
    second = publisher.publish_video(path="/video/migrants.mp4")
    assert first["id"] == second["id"] == "migrants.mp4"

    named = publisher.publish_video(
        path="/video/migrants.mp4", video_id=f"it-{uuid.uuid4().hex[:8]}"
    )
    assert named["id"] != first["id"]

    for submission in (first, named):
        event = _await_done(submission["id"])
        assert event.get("status") == "analysed", f"{submission['id']} did not complete"
