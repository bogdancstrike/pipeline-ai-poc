"""
`/pipeline/*` and `/workers/*` — the API that existed before the client app.

These drive the pipeline itself: submit a video, run a single worker, read the
wiring. With every MOCK_WORKER_* on, none of it touches the AI host, which is
the point of the switches — the whole topology is exercisable without
172.17.12.80.
"""

import uuid

import pytest

from support import live

pytestmark = pytest.mark.live

# Deliberately NOT the corpus prefix: a run id starting with `qa-` would land
# inside `seeded_only` and change the totals the records suite asserts.
RUN = f"probe-{uuid.uuid4().hex[:8]}"


# ── the wiring ───────────────────────────────────────────────────────────


def test_health_reports_kafka_and_what_is_mocked():
    answer = live.get("/pipeline/health")
    assert answer.ok

    assert answer.body["status"] in ("ok", "degraded")
    assert answer.body["kafka"], "a degraded pipeline has to name what it could not reach"
    assert answer.body["input_topic"] == "video.in"
    # Every service is on one list or the other, and never on both.
    mocked = set(answer.body["workers_mocked"])
    live_services = set(answer.body["workers_live"])
    assert mocked & live_services == set()
    assert len(mocked | live_services) == 7


def test_the_configuration_names_every_service_and_its_mode():
    body = live.get("/pipeline/config").body

    assert len(body["ai_services"]) == 5
    for name, url in body["ai_services"].items():
        assert url.startswith("http"), name
    assert body["mocked"]


def test_the_configuration_names_the_topics_the_workers_use():
    topics = live.get("/pipeline/config").body["topics"]
    assert len(topics) >= 7
    assert len(set(topics.values())) == len(topics), "two workers must not share a topic"


def test_the_configuration_reports_the_transcribe_defaults():
    body = live.get("/pipeline/config").body
    assert body["transcribe_defaults"]["language"]
    assert body["transcribe_defaults"]["task"] in ("translate", "transcribe")


def test_the_configuration_names_the_three_prompts():
    prompts = live.get("/pipeline/config").body["prompts"]
    assert len(prompts) >= 3


# ── the worker catalogue ─────────────────────────────────────────────────


def test_every_worker_is_listed_with_its_topics():
    body = live.get("/workers/list").body
    workers = {entry["worker"]: entry for entry in body["workers"]}

    assert len(workers) == 7, sorted(workers)
    for entry in workers.values():
        assert "topics_in" in entry and "topics_out" in entry
        assert isinstance(entry["mocked"], dict)


def test_the_catalogue_says_which_workers_run_first_when_chaining():
    workers = {entry["worker"]: entry for entry in live.get("/workers/list").body["workers"]}

    assert workers["splitter"]["runs_first"] == []
    assert len(workers["aggregator"]["runs_first"]) == 6, "the last one chains all of them"
    assert workers["face-match-main"]["runs_first"] == ["splitter"]


def test_the_two_aggregators_are_declared_as_aggregators():
    workers = {entry["worker"]: entry for entry in live.get("/workers/list").body["workers"]}
    assert workers["aggregator"]["kind"] == "aggregator"
    assert workers["aggregator-ai-caller"]["kind"] == "aggregator"
    assert workers["splitter"]["kind"] == "handler"


def test_the_final_aggregator_waits_on_both_the_face_branch_and_w6():
    workers = {entry["worker"]: entry for entry in live.get("/workers/list").body["workers"]}
    assert set(workers["aggregator"]["topics_in"]) == {"video.agg.face", "video.agg.ai"}


def test_the_splitter_fans_out_to_four_topics():
    workers = {entry["worker"]: entry for entry in live.get("/workers/list").body["workers"]}
    assert len(workers["splitter"]["topics_out"]) == 4


# ── running one worker ───────────────────────────────────────────────────


def test_running_one_worker_answers_with_what_it_produced():
    answer = live.post("/workers/face-match-main/run", {"path": "/video/migrants.mp4", "id": RUN})
    assert answer.ok, answer.text[:300]

    body = answer.body
    assert body["worker"] == "face-match-main"
    assert isinstance(body["result"]["face"]["persons"], list)


def test_the_answer_shows_the_message_the_worker_consumed():
    """So "what did :8823 actually see?" is answerable without a shell."""
    body = live.post("/workers/video-ocr/run", {"path": "/video/migrants.mp4", "id": RUN}).body

    assert body["consumed"]["path"] == "/video/migrants.mp4"
    assert body["chained"] is True
    assert body["ran_first"] == ["splitter"]


def test_the_answer_names_the_topics_it_would_have_published_to():
    body = live.post("/workers/face-match-main/run", {"path": "/video/x.mp4", "id": RUN}).body

    assert body["would_publish_to"] == ["video.agg.face"]
    assert body["published"] is False, "nothing reaches Kafka from a direct run"


def test_the_answer_reports_how_long_the_worker_took():
    body = live.post("/workers/face-match-main/run", {"path": "/video/x.mp4", "id": RUN}).body
    assert body["duration_ms"] >= 0


def test_running_a_worker_publishes_nothing_downstream():
    """The answer is the HTTP response; the corpus is untouched."""
    before = live.post("/client/records/search", {"page_size": 1}).body["total"]
    live.post("/workers/video-ocr/run", {"path": "/video/migrants.mp4", "id": RUN})
    after = live.post("/client/records/search", {"page_size": 1}).body["total"]

    assert after == before


@pytest.mark.parametrize(
    "worker",
    ["splitter", "face-match-main", "video-describe-354b", "transcribe", "video-ocr",
     "aggregator-ai-caller"],
)
def test_every_extraction_worker_runs_directly(worker):
    answer = live.post(f"/workers/{worker}/run", {"path": "/video/migrants.mp4", "id": RUN})
    assert answer.ok, f"{worker}: {answer.text[:200]}"


def test_chaining_runs_the_whole_pipeline_inside_one_request():
    answer = live.post(
        "/workers/aggregator/run",
        {"path": "/video/migrants.mp4", "id": RUN, "chain": True, "persist": False},
        timeout=120,
    )
    assert answer.ok, answer.text[:300]

    result = answer.body["result"]
    record = result["record"]

    assert answer.body["ran_first"] == [
        "splitter", "face-match-main", "video-describe-354b",
        "transcribe", "video-ocr", "aggregator-ai-caller",
    ]
    assert record["enrichment"]["summary"]["text"]
    assert record["enrichment"]["sentiment"]["text"] == "NEGATIVE"
    assert record["enrichment"]["entities"]["list"]
    assert result["persons"] and result["entities"]


def test_the_chained_run_reports_the_same_status_the_record_carries():
    answer = live.post(
        "/workers/aggregator/run",
        {"path": "/video/migrants.mp4", "id": RUN, "chain": True, "persist": False},
        timeout=120,
    )
    result = answer.body["result"]
    assert result["status"] == ("partial" if result["failed_services"] else "analysed")


def test_a_trial_run_of_the_aggregator_writes_no_record():
    """`persist` off is what keeps a trial from overwriting a real answer."""
    trial_id = f"{RUN}-trial"
    live.post(
        "/workers/aggregator/run",
        {"path": "/video/migrants.mp4", "id": trial_id, "chain": True, "persist": False},
        timeout=120,
    )
    assert live.get(f"/client/records/{trial_id}").status == 404


def test_a_worker_can_be_fed_a_message_verbatim():
    """How to re-run W6 over branches you already have, without re-extracting."""
    answer = live.post(
        "/workers/aggregator-ai-caller/run",
        {
            "id": RUN,
            "message": {
                "id": RUN,
                "path": "/video/migrants.mp4",
                "name": "migrants.mp4",
                "describe": {"text": "a wide shot of the breakwater"},
                "transcript": {"text": "hello", "format": "dialog"},
                "ocr": {"text": "ON SCREEN", "frames_count": 3},
            },
        },
        timeout=60,
    )
    assert answer.ok, answer.text[:300]
    assert answer.body["chained"] is False, "an explicit message implies chain=false"


def test_a_worker_that_does_not_exist_is_a_404_that_says_where_to_look():
    answer = live.post("/workers/no-such-worker/run", {"path": "/video/x.mp4"})
    assert answer.status == 404
    assert "workers/list" in answer.text


def test_running_a_worker_with_neither_a_path_nor_a_message_is_a_400():
    answer = live.post("/workers/face-match-main/run", {})
    assert answer.status == 400
    assert "path" in answer.text


def test_a_message_that_is_not_an_object_is_refused():
    answer = live.post("/workers/summary/run", {"message": "a string"})
    assert answer.status == 400


# ── submitting a video ───────────────────────────────────────────────────


def test_submitting_a_video_is_accepted_and_names_the_run():
    answer = live.post("/pipeline/analyze", {"path": "/video/migrants.mp4", "id": RUN})
    assert answer.status == 202, answer.text[:300]

    assert answer.body["id"] == RUN
    assert answer.body["status"] == "submitted"
    assert answer.body["output_file"].endswith("_analysis.json")


def test_the_submission_reports_which_workers_are_mocked():
    answer = live.post("/pipeline/analyze", {"path": "/video/migrants.mp4", "id": f"{RUN}-2"})
    assert "mocked_workers" in answer.body


def test_the_submission_reports_the_transcribe_parameters_it_will_use():
    answer = live.post(
        "/pipeline/analyze",
        {"path": "/video/migrants.mp4", "id": f"{RUN}-3", "options": {"language": "es"}},
    )
    assert answer.body["transcribe_params"]["language"] == "es"


def test_an_unrecognised_option_is_dropped_rather_than_forwarded():
    answer = live.post(
        "/pipeline/analyze",
        {"path": "/video/migrants.mp4", "id": f"{RUN}-4", "options": {"nonsense": "x"}},
    )
    assert answer.status == 202
    assert "nonsense" not in answer.body["transcribe_params"]


def test_a_submission_without_a_path_is_a_400_that_shows_one():
    answer = live.post("/pipeline/analyze", {})
    assert answer.status == 400
    assert "path" in answer.text


def test_an_empty_path_is_a_400():
    assert live.post("/pipeline/analyze", {"path": "   "}).status == 400


def test_options_that_are_not_an_object_are_refused():
    answer = live.post("/pipeline/analyze", {"path": "/video/x.mp4", "options": "es"})
    assert answer.status == 400


def test_a_path_the_app_cannot_see_is_still_forwarded():
    """VIDEO_PATH_PASSTHROUGH: the services resolve it on their own filesystem."""
    answer = live.post(
        "/pipeline/analyze",
        {"path": "/video/only-on-the-ai-host.mp4", "id": f"{RUN}-5"},
    )
    assert answer.status == 202


# ── the whole pipeline, over Kafka ───────────────────────────────────────


def test_a_submitted_video_becomes_a_record(stack):
    """The real thing: submit, and wait for W7's row to appear."""
    run_id = f"{RUN}-full"
    submitted = live.post("/pipeline/analyze", {"path": "/video/migrants.mp4", "id": run_id})
    assert submitted.status == 202

    record = live.wait_for(
        lambda: (lambda a: a.body if a.ok else None)(live.get(f"/client/records/{run_id}")),
        timeout=90,
        what=f"the record for {run_id}",
    )

    assert record["status"] in ("analysed", "partial")
    assert record["summary"]
    assert record["calls"], "the provenance W6 collected has to reach the row"

    live.delete(f"/client/records/{run_id}")  # best effort; 405 is fine
