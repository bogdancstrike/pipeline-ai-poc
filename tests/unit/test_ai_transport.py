"""
`ai_client` — how the pipeline talks to the five services, and gives up.

No socket is opened here: `requests.post` is replaced. What is under test is
the policy — which failures are retried, which fail at once, what the error
says — because that policy is the difference between one slow service and a
pipeline that stalls.
"""

import json

import pytest
import requests

import ai_client
from ai_client import AIServiceError
from config import Config


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self.content = self.text.encode("utf-8")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


@pytest.fixture()
def transport(monkeypatch):
    """Record every POST and answer with a scripted sequence."""
    calls = []
    answers = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, "json": kwargs.get("json"), "timeout": kwargs.get("timeout")})
        answer = answers.pop(0) if answers else FakeResponse(200, {"ok": True})
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(ai_client.requests, "post", fake_post)
    # Retries sleep between attempts; the policy is what is under test, not the wait.
    monkeypatch.setattr(Config, "AI_RETRY_BACKOFF_SEC", 0.0)
    monkeypatch.setattr(ai_client.time, "sleep", lambda _seconds: None)

    class Transport:
        def script(self, *responses):
            answers.clear()
            answers.extend(responses)

        @property
        def calls(self):
            return calls

    return Transport()


def live(monkeypatch, *services):
    """Turn the mock switch off for the named services."""
    flags = {
        "face": "MOCK_WORKER_FACE_MATCH",
        "describe": "MOCK_WORKER_DESCRIBE",
        "ocr": "MOCK_WORKER_OCR",
        "transcribe": "MOCK_WORKER_TRANSCRIBE",
        "summary": "MOCK_WORKER_SUMMARY",
    }
    for name in services:
        monkeypatch.setattr(Config, flags[name], False)


# ── the request each service gets ────────────────────────────────────────


def test_face_match_posts_the_path_to_match(transport, monkeypatch):
    live(monkeypatch, "face")
    transport.script(FakeResponse(200, {"persons": ["222"], "message": "ok"}))

    answer = ai_client.face_match("/video/x.mp4", video_id="vid-1")

    assert transport.calls[0]["url"].endswith("/match")
    assert transport.calls[0]["json"] == {"path": "/video/x.mp4"}
    assert answer["data"]["persons"] == ["222"]


def test_the_path_is_forwarded_byte_for_byte(transport, monkeypatch):
    """The services resolve it on their own filesystem; nothing is rewritten."""
    live(monkeypatch, "face")
    transport.script(FakeResponse(200, {"persons": []}))

    ai_client.face_match("/data/audio/dockers/CNI/VIDEOS/Inmigracion/1abe.mp4")

    assert transport.calls[0]["json"]["path"] == (
        "/data/audio/dockers/CNI/VIDEOS/Inmigracion/1abe.mp4"
    )


def test_describe_posts_to_describe(transport, monkeypatch):
    live(monkeypatch, "describe")
    transport.script(FakeResponse(200, {"description": "a wide shot"}))

    ai_client.describe("/video/x.mp4")
    assert transport.calls[0]["url"].endswith("/describe")


def test_ocr_posts_to_ocr(transport, monkeypatch):
    live(monkeypatch, "ocr")
    transport.script(FakeResponse(200, {"text": "BREAKING"}))

    ai_client.ocr("/video/x.mp4")
    assert transport.calls[0]["url"].endswith("/ocr")


def test_transcribe_carries_the_env_defaults(transport, monkeypatch):
    live(monkeypatch, "transcribe")
    transport.script(FakeResponse(200, {"transcription": "hello"}))

    ai_client.transcribe("/video/x.mp4")

    body = transport.calls[0]["json"]
    assert body["path"] == "/video/x.mp4"
    assert body["language"] == Config.TRANSCRIBE_LANGUAGE
    assert body["task"] == Config.TRANSCRIBE_TASK


def test_a_per_submit_override_wins_over_the_env(transport, monkeypatch):
    live(monkeypatch, "transcribe")
    transport.script(FakeResponse(200, {"transcription": "hola"}))

    ai_client.transcribe("/video/x.mp4", {"language": "es", "task": "transcribe"})

    body = transport.calls[0]["json"]
    assert body["language"] == "es"
    assert body["task"] == "transcribe"


def test_an_unrecognised_override_is_ignored_rather_than_forwarded():
    """The services reject an unknown key; the allow-list is the guard."""
    params = ai_client.transcribe_params({"language": "ro", "nonsense": "x"})
    assert params["language"] == "ro"
    assert "nonsense" not in params


def test_the_request_carries_the_configured_timeout(transport, monkeypatch):
    live(monkeypatch, "face")
    transport.script(FakeResponse(200, {"persons": []}))

    ai_client.face_match("/video/x.mp4")
    assert transport.calls[0]["timeout"] == Config.AI_TIMEOUT_SEC


# ── which failures are retried ───────────────────────────────────────────


def test_a_connection_error_is_retried(transport, monkeypatch):
    live(monkeypatch, "face")
    monkeypatch.setattr(Config, "AI_RETRIES", 2)
    transport.script(
        requests.ConnectionError("connection reset"),
        requests.ConnectionError("connection reset"),
        FakeResponse(200, {"persons": ["222"]}),
    )

    answer = ai_client.face_match("/video/x.mp4")

    assert len(transport.calls) == 3
    assert answer["data"]["persons"] == ["222"]


def test_a_5xx_is_retried_because_the_model_may_still_be_loading(transport, monkeypatch):
    live(monkeypatch, "describe")
    monkeypatch.setattr(Config, "AI_RETRIES", 1)
    transport.script(
        FakeResponse(503, text="loading"),
        FakeResponse(200, {"description": "ready now"}),
    )

    answer = ai_client.describe("/video/x.mp4")

    assert len(transport.calls) == 2
    assert answer["data"]["description"] == "ready now"


def test_a_4xx_fails_at_once_because_the_request_is_ours(transport, monkeypatch):
    live(monkeypatch, "face")
    monkeypatch.setattr(Config, "AI_RETRIES", 3)
    transport.script(
        FakeResponse(400, text='{"detail":"path /video/x.mp4 does not exist"}'),
    )

    with pytest.raises(AIServiceError) as caught:
        ai_client.face_match("/video/x.mp4")

    assert len(transport.calls) == 1, "a bad path must not be retried four times"
    # The message has to carry the service's own words, or nobody can act on it.
    assert "does not exist" in str(caught.value)
    assert "400" in str(caught.value)


def test_giving_up_names_the_service_the_url_and_the_attempts(transport, monkeypatch):
    live(monkeypatch, "face")
    monkeypatch.setattr(Config, "AI_RETRIES", 1)
    transport.script(
        requests.ConnectionError("no route to host"),
        requests.ConnectionError("no route to host"),
    )

    with pytest.raises(AIServiceError) as caught:
        ai_client.face_match("/video/x.mp4")

    message = str(caught.value)
    assert "face-match-main" in message
    assert "/match" in message
    assert "2 attempt" in message


def test_a_non_json_body_from_a_2xx_is_an_error_not_a_crash(transport, monkeypatch):
    live(monkeypatch, "face")
    transport.script(FakeResponse(200, payload=None, text="<html>proxy error</html>"))

    with pytest.raises(AIServiceError) as caught:
        ai_client.face_match("/video/x.mp4")

    assert "non-JSON" in str(caught.value)


def test_a_json_body_that_is_not_an_object_is_refused(transport, monkeypatch):
    live(monkeypatch, "face")
    transport.script(FakeResponse(200, payload=["not", "an", "object"]))

    with pytest.raises(AIServiceError):
        ai_client.face_match("/video/x.mp4")


# ── the mock switch ──────────────────────────────────────────────────────


def test_a_mocked_service_opens_no_socket(transport):
    """Every MOCK_WORKER_* is on in the test environment."""
    answer = ai_client.face_match("/video/x.mp4")

    assert transport.calls == []
    assert answer["meta"]["mocked"] is True
    assert answer["meta"]["endpoint"] is None


def test_a_mocked_answer_has_the_shape_of_a_real_one():
    mocked = ai_client.transcribe("/video/x.mp4")
    assert set(mocked) == {"data", "meta"}
    assert "transcription" in mocked["data"]


def test_the_meta_reports_the_endpoint_for_a_live_call(transport, monkeypatch):
    live(monkeypatch, "face")
    transport.script(FakeResponse(200, {"persons": []}))

    meta = ai_client.face_match("/video/x.mp4")["meta"]

    assert meta["mocked"] is False
    assert meta["endpoint"].endswith("/match")
    assert meta["duration_ms"] >= 0
    assert meta["service"] == "face-match-main"
