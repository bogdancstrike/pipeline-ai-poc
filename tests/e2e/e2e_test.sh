#!/usr/bin/env bash
#
# End-to-end smoke test against a running stack.
#
#   docker compose up -d --build
#   tests/e2e/e2e_test.sh                      # uses /video/migrants.mp4
#   VIDEO=/app/videos/clip.mp4 tests/e2e/e2e_test.sh
#
# Two phases, both against the running stack:
#
#   1. the pipeline  — submit one video, wait for the record W7 writes
#   2. the workers   — run each of the seven directly through
#                      POST /workers/{worker}/run and check that the answer
#                      comes back in the response and NOTHING is published
#
# With MOCK_WORKER_*=True in .env this needs nothing but the compose stack;
# with the real services it needs the AI host to be reachable from the app
# container.
set -euo pipefail

API="${API:-http://localhost:5000}"
VIDEO="${VIDEO:-/video/migrants.mp4}"
VIDEO_ID="${VIDEO_ID:-e2e-$(date +%s)}"
OUTPUT_DIR="${OUTPUT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)/output}"
TIMEOUT_SEC="${TIMEOUT_SEC:-180}"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }

step "health"
health="$(curl -fsS "$API/pipeline/health")" || fail "API not reachable at $API"
echo "$health"
echo "$health" | grep -q '"status": *"ok"' || fail "pipeline reports degraded — is Kafka up?"

step "wiring"
curl -fsS "$API/pipeline/config" | head -40

step "submit $VIDEO (id=$VIDEO_ID)"
submit="$(curl -fsS -X POST "$API/pipeline/analyze" \
  -H 'Content-Type: application/json' \
  -d "{\"id\":\"$VIDEO_ID\",\"path\":\"$VIDEO\"}")" || fail "submit rejected"
echo "$submit"

expected="$(printf '%s' "$submit" | python3 -c 'import json,sys; print(json.load(sys.stdin)["output_file"])')"
# The API reports the path inside the container; read it on the host mount.
host_file="$OUTPUT_DIR/$(basename "$expected")"
echo "waiting for $host_file"

step "wait for the record (max ${TIMEOUT_SEC}s)"
# A previous run of the same video leaves a record at this exact path, so wait
# for one whose id is OURS rather than for the file to merely exist.
deadline=$(( $(date +%s) + TIMEOUT_SEC ))
until [ -f "$host_file" ] && python3 -c "
import json,sys
try: sys.exit(0 if json.load(open(sys.argv[1], encoding='utf-8')).get('id') == sys.argv[2] else 1)
except Exception: sys.exit(1)
" "$host_file" "$VIDEO_ID"; do
  [ "$(date +%s)" -lt "$deadline" ] || fail "no record for $VIDEO_ID after ${TIMEOUT_SEC}s — check: docker compose logs app"
  sleep 2
done

step "verify the record"
python3 - "$host_file" "$VIDEO_ID" <<'PY'
import json, sys

record = json.load(open(sys.argv[1], encoding="utf-8"))
assert record["id"] == sys.argv[2], f"record is for {record['id']}, expected {sys.argv[2]}"

expected = {"id", "name", "path", "submitted_at", "analysed_at", "enrichment", "errors"}
assert set(record) == expected, f"record keys are {sorted(record)}, expected {sorted(expected)}"

enrichment = record["enrichment"]
for key in ("face_match", "description", "transcript", "ocr", "summary", "entities", "sentiment"):
    assert key in enrichment, f"enrichment is missing {key}"

assert not record["errors"], f"services failed: {record['errors']}"

print(f"  id        : {record['id']}")
print(f"  persons   : {enrichment['face_match']['persons']}")
print(f"  entities  : {enrichment['entities']['list']}")
print(f"  sentiment : {enrichment['sentiment']['text']}")
print(f"  summary   : {enrichment['summary']['text'][:90]}...")
PY

# ---------------------------------------------------------------------------
# Phase 2 — the same seven workers, one at a time, straight from the API.
#
# The checkers are written to temp files because each one reads the response
# from stdin: a heredoc would occupy the same stdin the pipe needs.
# ---------------------------------------------------------------------------

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

cat > "$workdir/show_list.py" <<'PY'
import json, sys

for w in json.load(sys.stdin)["workers"]:
    mocked = ", ".join(f"{k}={v}" for k, v in w["mocked"].items()) or "no AI call"
    print(f"  {w['step']} {w['worker']:<22} {w['kind']:<10} {mocked}")
PY

cat > "$workdir/check_run.py" <<'PY'
import json, sys

worker = sys.argv[1]
answer = json.load(sys.stdin)

assert answer["worker"] == worker, f"answered for {answer['worker']}"
assert answer["published"] is False, "a direct run must publish nothing"
assert answer["would_publish_to"], "every worker declares topics_out"
assert isinstance(answer["result"], dict) and answer["result"], "empty result"

print(f"  ran first        : {', '.join(answer['ran_first']) or 'nothing'}")
print(f"  would publish to : {', '.join(answer['would_publish_to'])}  (published: {answer['published']})")
print(f"  took             : {answer['duration_ms']}ms")
PY

cat > "$workdir/check_sync.py" <<'PY'
import json, sys

result = json.load(sys.stdin)["result"]
record = result["record"]
enrichment = record["enrichment"]

assert enrichment["face_match"]["persons"] is not None, "no face match in the record"
assert result["output_file"] is None, "persist defaults to false — nothing should be written"

print(f"  entities    : {enrichment['entities']['list']}")
print(f"  sentiment   : {enrichment['sentiment']['text']}")
print(f"  output_file : {result['output_file']}  (persist defaults to false)")
PY

step "list the workers"
curl -fsS "$API/workers/list" | python3 "$workdir/show_list.py" || fail "/workers/list did not answer"

for worker in splitter face-match-main video-describe-354b transcribe video-ocr \
              aggregator-ai-caller aggregator; do
  step "run $worker directly"
  curl -fsS -X POST "$API/workers/$worker/run" \
    -H 'Content-Type: application/json' \
    -d "{\"id\":\"$VIDEO_ID-$worker\",\"path\":\"$VIDEO\"}" \
    | python3 "$workdir/check_run.py" "$worker" || fail "$worker did not answer as expected"
done

step "the final aggregator returns the whole record, and writes no file"
curl -fsS -X POST "$API/workers/aggregator/run" \
  -H 'Content-Type: application/json' \
  -d "{\"id\":\"$VIDEO_ID-sync\",\"path\":\"$VIDEO\"}" \
  | python3 "$workdir/check_sync.py" || fail "the synchronous run did not answer as expected"

step "an unknown worker is a 404"
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/workers/nope/run" \
  -H 'Content-Type: application/json' -d '{"path":"'"$VIDEO"'"}')"
[ "$code" = "404" ] || fail "expected 404 for an unknown worker, got $code"
echo "  404 as expected"

printf '\n\033[32mPASS\033[0m — pipeline record at %s, and all 7 workers answered directly\n' "$host_file"
