"""
Talking to a running stack.

The integration, performance and load suites drive the API over HTTP rather
than importing it, for the same reason the E2E suite drives a browser: what is
under test is the deployed thing — the compose network, the JSON on the wire,
the status codes Flask-RESTX actually returns — and an in-process test client
answers questions about none of that.

`API_BASE` points it somewhere else (another host, the frontend's nginx proxy);
everything auto-skips when nothing answers, so the unit suite still runs on a
laptop with no Docker.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

API_BASE = os.getenv("API_BASE", "http://localhost:5696").rstrip("/")
TIMEOUT = float(os.getenv("API_TIMEOUT_SEC", "30"))


class Answer:
    """One HTTP answer, already parsed when it is JSON."""

    __slots__ = ("status", "headers", "body", "text", "elapsed_ms", "url")

    def __init__(self, status: int, headers, body: Any, text: str, elapsed_ms: float, url: str):
        self.status = status
        self.headers = headers
        self.body = body
        self.text = text
        self.elapsed_ms = elapsed_ms
        self.url = url

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def __repr__(self) -> str:  # pragma: no cover - test output only
        return f"<{self.status} {self.url} in {self.elapsed_ms:.0f}ms>"


def request(
    method: str,
    path: str,
    *,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Answer:
    """One request, answering with the status even when it is an error.

    urllib raises on 4xx/5xx; a test that asserts "this is a 400" should not
    have to catch an exception to find out.
    """
    url = f"{API_BASE}{path}"
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"accept": "application/json"}
    if payload is not None:
        request_headers["content-type"] = "application/json"
    request_headers.update(headers or {})

    req = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as response:
            status, raw, response_headers = response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        status, raw, response_headers = exc.code, exc.read(), exc.headers
    elapsed_ms = (time.perf_counter() - started) * 1000

    text = raw.decode("utf-8", "replace")
    try:
        parsed = json.loads(text) if text else None
    except ValueError:
        parsed = None

    return Answer(status, response_headers, parsed, text, elapsed_ms, url)


def get(path: str, **kwargs) -> Answer:
    return request("GET", path, **kwargs)


def post(path: str, body: Optional[Dict[str, Any]] = None, **kwargs) -> Answer:
    return request("POST", path, body=body if body is not None else {}, **kwargs)


def put(path: str, body: Optional[Dict[str, Any]] = None, **kwargs) -> Answer:
    return request("PUT", path, body=body if body is not None else {}, **kwargs)


def delete(path: str, **kwargs) -> Answer:
    return request("DELETE", path, **kwargs)


def raw(path: str, *, timeout: Optional[float] = None) -> Tuple[int, bytes, Any]:
    """A download, as bytes — an export is not JSON."""
    req = urllib.request.Request(f"{API_BASE}{path}", headers={"accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers


def reachable() -> bool:
    """Is the stack up? Answers rather than raises, for a skip condition."""
    try:
        return get("/client/health", timeout=3).status < 500
    except Exception:
        return False


def wait_for(condition, *, timeout: float = 60.0, interval: float = 1.0, what: str = "condition"):
    """Poll until `condition()` is truthy, and return what it answered."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = condition()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"{what} did not happen within {timeout}s (last answer: {last!r})")
