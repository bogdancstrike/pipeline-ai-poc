"""
Call any worker directly, with no Kafka in the loop.

Why this is possible at all
---------------------------
`@kafka_handler` / `@kafka_aggregator` do not wrap the function they decorate:
they register a `WorkerSpec` (which keeps a reference to the function) and
return the function unchanged. Publishing a worker's return value to its
`topics_out` is done by the framework's ETL runtime *around* that call, never
inside it.

So invoking `spec.fn(message, consumer_name, metadatas)` from anywhere runs the
exact same worker body the pipeline runs, and its return value is just a Python
dict. **Nothing is produced to Kafka, nothing is buffered in Redis.** That is
the whole mechanism behind `POST /workers/{worker}/run`; the framework is used
as-is, with no modification and no private API beyond its public registry.

Building the input
------------------
Each worker expects the message *its own* topic carries, which is the output of
the worker upstream of it. Rather than hard-coding those shapes, this module
reads the topic graph out of the registry: for every `topics_in` of the target
worker, it finds the worker that publishes to that topic and runs it first,
recursively, deep-merging the branches exactly as the aggregator runtime would.

    POST /workers/video-ocr/run        -> W1, then W5
    POST /workers/aggregator/run       -> W1, W2, W3, W4, W5, W6, then W7

Each worker runs at most once per request (the results are cached by name), so
the splitter is not re-run four times. `chain=false` skips all of that and hands
the request body to the worker untouched, for when you want to drive one worker
with a message you wrote yourself.

Mocking is unchanged: a worker whose `MOCK_WORKER_*` flag is on answers with the
canned body from `src/mock/mock_responses.py` here exactly as it does in the
pipeline, because the flag is checked inside `ai_client`, below the worker.
"""

import copy
import importlib
import time
from typing import Any, Dict, List, Optional, Tuple

from framework.commons.utils import deep_merge
from framework.decorators.kafka_workers import WorkerSpec, all_workers

from config import Config

# The module whose import registers the seven workers. Importing it here means
# the catalog is correct even when the ETL thread is disabled or still starting.
WORKER_MODULE = "workers.pipeline"


class UnknownWorker(LookupError):
    """No worker is registered under that name."""


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

def _specs() -> List[WorkerSpec]:
    """Every registered worker, in pipeline order (W1 … W7)."""
    importlib.import_module(WORKER_MODULE)  # idempotent; registers on first import
    return sorted(all_workers(), key=lambda spec: spec.metadatas.get("step", 99))


def _spec(name: str) -> WorkerSpec:
    for spec in _specs():
        if spec.name == name:
            return spec
    raise UnknownWorker(f"unknown worker {name!r} — known: {[s.name for s in _specs()]}")


def _producer_of(topic: str) -> Optional[WorkerSpec]:
    """The worker that publishes to `topic`, or None for a pipeline entry point."""
    for spec in _specs():
        if topic in spec.topics_out:
            return spec
    return None


def catalog() -> List[dict]:
    """Every worker with its wiring — what `GET /workers/list` serves."""
    flags = Config.mock_flags()
    return [
        {
            "worker": spec.name,
            "step": spec.metadatas.get("step"),
            "kind": spec.kind,
            "topics_in": list(spec.topics_in),
            "topics_out": list(spec.topics_out),
            "aggregate_by": spec.aggregate_by,
            # Which upstream workers a chained call will run before this one.
            "runs_first": [s.name for s in _upstream(spec)],
            # Per AI call this worker makes: is MOCK_WORKER_<NAME> on? `{}` for
            # a worker that calls no service at all (W1, W7). A mocked call
            # answers from src/mock/mock_responses.py here exactly as it does
            # in the pipeline.
            "mocked": {
                call: flags.get(call) for call in spec.metadatas.get("ai_calls", [])
            },
            "run": f"POST /workers/{spec.name}/run",
        }
        for spec in _specs()
    ]


def _upstream(spec: WorkerSpec, _walking: Tuple[str, ...] = ()) -> List[WorkerSpec]:
    """The workers a chained call runs before `spec`, in order, without repeats.

    The topic graph is a DAG, but nothing in the framework enforces that — so a
    cycle is reported as a cycle rather than as a stack overflow.
    """
    if spec.name in _walking:
        raise UnknownWorker(
            f"the topics of {' -> '.join(_walking + (spec.name,))} form a cycle; "
            f"call it with chain=false and supply the message yourself"
        )

    ordered: List[WorkerSpec] = []
    for topic in spec.topics_in:
        producer = _producer_of(topic)
        if producer is None:
            continue
        for earlier in _upstream(producer, _walking + (spec.name,)) + [producer]:
            if earlier.name not in {s.name for s in ordered}:
                ordered.append(earlier)
    return ordered


# ---------------------------------------------------------------------------
# Running one worker
# ---------------------------------------------------------------------------

def _invoke(spec: WorkerSpec, message: dict, persist: bool) -> Any:
    """Call the worker body itself. This is the line that bypasses Kafka.

    `metadatas` is the decorator's dict plus two facts the ETL never sets, so a
    worker can tell it was reached over HTTP — W7 reads `persist` and skips
    writing the record file when it is False.
    """
    metadatas = {**spec.metadatas, "invoked_via": "api", "persist": persist}
    return spec.fn(message, Config.WORKER_NAME, metadatas)


def _input_for(spec: WorkerSpec, seed: dict, done: Dict[str, Any]) -> dict:
    """Rebuild the message `spec` consumes by running everything upstream of it.

    One branch per entry in `topics_in`, deep-merged — the same fan-in the
    framework performs from Redis before it invokes an aggregator.
    """
    merged: dict = {}
    for topic in spec.topics_in:
        producer = _producer_of(topic)
        if producer is None:
            branch = seed  # a pipeline entry point: the submitted message itself
        else:
            if producer.name not in done:
                done[producer.name] = _invoke(
                    producer, _input_for(producer, seed, done), persist=False
                )
            branch = done[producer.name]
        merged = deep_merge(merged, copy.deepcopy(branch))
    return merged


def run(
    name: str,
    seed: dict,
    *,
    chain: bool = True,
    persist: bool = False,
) -> dict:
    """Run one worker synchronously and return what it produced.

    `seed` is the submitted message (`id`, `path`, `name`, `options`).

    `chain=True` runs the upstream workers first so the target receives the
    message its topic would have carried; `chain=False` passes `seed` straight
    in, so you can hand a worker a message you assembled yourself.

    `persist=True` lets W7 write its record file, as it does in the pipeline.
    """
    spec = _spec(name)
    # Resolved first: it is also what rejects a cyclic topic graph, before any
    # worker body runs.
    ran_first = [s.name for s in _upstream(spec)] if chain else []

    message = _input_for(spec, seed, {}) if chain else copy.deepcopy(seed)

    started = time.monotonic()
    result = _invoke(spec, message, persist)
    duration_ms = round((time.monotonic() - started) * 1000, 1)

    return {
        "worker": spec.name,
        "kind": spec.kind,
        "chained": chain,
        "ran_first": ran_first,
        "duration_ms": duration_ms,
        # In the pipeline the result would go to these topics. Not here.
        "would_publish_to": list(spec.topics_out),
        "published": False,
        "consumed": message,
        "result": result,
    }
