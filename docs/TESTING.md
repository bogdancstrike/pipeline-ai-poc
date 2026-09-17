# Testing

Five suites, one stack, 825 tests. This is what is covered, what it found, and
how to run any of it.

```
                          tests     needs                      takes
  unit         pytest       396     nothing                     0.4s
  existing     pytest        74     Kafka + Redis for 2 of them 10s
  integration  pytest       177     the compose stack           6s
  e2e          Playwright   147     the compose stack          44s
  performance  pytest        19     the compose stack           4s
  load         pytest        12     the compose stack          82s
```

All of it passes. Six defects were found on the way, five of them fixed; the
sixth is a judgement call that is pinned rather than changed. They are listed
under [What it found](#what-it-found), each with the test that now stands where
it was.

---

## Running it

```bash
# once
python -m venv .venv && .venv/bin/pip install ./dist/qf-1.0.5-py3-none-any.whl
.venv/bin/pip install -r requirements.txt
(cd tests/e2e && npm install && npx playwright install chromium)

docker compose up -d                       # everything below wants this

.venv/bin/python -m pytest                 # all the Python suites
.venv/bin/python -m pytest -m "not live"   # only what needs no stack
.venv/bin/python -m pytest -m perf -s      # with the numbers printed
.venv/bin/python -m pytest -m load -s
(cd tests/e2e && npx playwright test)      # the browser suite
(cd tests/e2e && npx playwright show-report)
```

Markers, from `pytest.ini`:

| marker        | means                                                        |
| ------------- | ------------------------------------------------------------ |
| *(none)*      | a unit test — one module, no infrastructure, no network       |
| `integration` | needs Kafka and Redis (`docker compose up -d kafka redis`)    |
| `live`        | needs the whole stack answering on `API_BASE`                 |
| `perf`        | measures how long something takes, and fails when it is slow  |
| `load`        | drives concurrent traffic at the running stack                |

Everything that needs the stack **skips** rather than fails when it is not
there, so `pytest` on a laptop with no Docker still runs the 396 unit tests.

### Pointing it somewhere else

```bash
API_BASE=http://10.0.0.5:5696 .venv/bin/python -m pytest -m live
E2E_BASE_URL=http://10.0.0.5:5697 npx playwright test
QA_CORPUS_SIZE=500 .venv/bin/python -m pytest -m live
```

---

## The corpus everything is asked about

`tests/support/corpus.py` builds records in W7's own shape;
`tests/support/seed.py` writes them through `client.store.save_record` — the
same writer the pipeline uses — so a seeded row is a row the pipeline could
have produced, and a change to the flattening is caught by the seeder rather
than in production.

```bash
python tests/support/seed.py seed --count 120
python tests/support/seed.py count
python tests/support/seed.py clear      # removes only what it wrote
```

120 records, deterministic, and **varied on purpose** — a hundred copies of one
record proves a filter returns rows, not that it filters:

| dimension | spread                                                  |
| --------- | ------------------------------------------------------- |
| sentiment | 40 NEGATIVE, 40 POSITIVE, 40 NEUTRAL                    |
| status    | 100 analysed, 20 partial (three different failures)     |
| model     | three, evenly                                            |
| persons   | 0, 1 or 2 per record; 120 mentions of four people        |
| entities  | 2–5 per record, 420 mentions, four types                 |
| calls     | every fourth record is a *live* run, the rest mocked     |
| time      | record 0 is now, each one 6h older — 30 days in all      |

Every id starts with `qa-`, which is what makes seeding idempotent and reversible
without touching a record a real run produced. `corpus.expected(n)` computes the
totals from the same cycles the records are built from, so a test asserts a
number rather than a shape — and a change to the generator can never quietly
agree with a change to the app.

---

## What each suite covers

### Unit — 396 tests, `tests/unit/`, 0.4 seconds

One module each, no infrastructure. Grouped by what would be wrong:

| file | tests | what it pins |
| --- | ---: | --- |
| `test_video_paths.py` | 18 | the three branches of `resolve_video_path`, including that a *relative* path is expanded against the working directory — which is how a host path reaches services that resolve it on their own filesystem |
| `test_query_vocabulary.py` | 67 | every alias the query builder may send maps to one canonical operator; each kind only offers operators it can honour; no filter value or sort name reaches the SQL uninterpolated |
| `test_condition_trees.py` | 28 | the compiled SQL and the sentence shown above the results skip the same unfinished rules — a reader told "Sentiment is NEGATIVE" and shown other rows has no way to know which half lied |
| `test_export_files.py` | 42 | the BOM Excel needs, formula defusing, null-vs-blank between CSV and JSON, the zip container actually holding the values |
| `test_media_resolution.py` | 29 | tail matching, and the traversal, symlink and prefix-sibling refusals that make it safe to serve a file named by a database row |
| `test_record_flattening.py` | 36 | sentiment case, entity splitting, person counts, character counts, truncation to the column width |
| `test_ai_transport.py` | 17 | a 5xx is retried, a 4xx is not, and the error carries the service's own words |
| `test_clock_and_ranges.py` | 25 | every window the picker offers, and its boundaries |
| `test_pagination_envelope.py` | 24 | "page 7 of 42", and the ceiling that stops a client deciding how much work the database does |
| `test_configuration.py` | 31 | env booleans are booleans, topics are distinct, every worker has a mock switch |
| `test_record_sinks.py` | 21 | the file is written atomically and named after the video; a submission is keyed by its run id |
| `test_prompt_loading.py` | 15 | the stored wording wins over the file, and a database outage cannot stop a video being analysed |
| `test_mock_answers.py` | 14 | the canned answers have the shape of the real ones — they *are* the pipeline for most runs |
| `test_corpus_fixture.py` | 22 | the fixture tests itself, so a broken generator cannot make a broken app look correct |

### Existing suite — 74 tests, `tests/test_*.py`

Shipped with the project; four stale assertions fixed (below). Two of them are
`integration`-marked and run the whole seven-worker topology over real Kafka and
Redis with every AI service mocked.

### Integration — 177 tests, `tests/integration/`

The API over HTTP, not through an in-process test client: what is under test is
the deployed thing — the compose network, the JSON on the wire, the status codes
Flask-RESTX actually returns.

* **records (50)** — the envelope; paging through the whole corpus exactly once;
  server-side sort; the filter bar; free text reaching the transcript and the
  on-screen text; facets; condition trees; one record's enrichment and
  provenance; the 404s
* **dashboard and statistics (37)** — every tile says which direction is good;
  every series has one value per label; a narrower window cannot hold more than a
  wider one; live and mocked never double-count; p95 ≥ median ≥ nothing
* **pipeline and workers (37)** — the seven-worker catalogue and its chain order;
  one worker run directly publishing nothing; the aggregator running the whole
  pipeline inside one request; a trial run writing no record; **a submitted video
  becoming a row**, over Kafka, end to end
* **saved searches and prompts (27)** — the full lifecycle of the two things a
  reader can write, restoring the shipped prompt wording afterwards
* **exports, meta, health, errors (26)** — the BOM, the content types, the
  filename header, and that every format `/client/meta` advertises can actually
  be produced

### End-to-end — 147 tests, `tests/e2e/`

Playwright, against **nginx on the frontend origin** rather than the Vite dev
server. That is not a detail: nginx is what proxies `/client`, `/pipeline` and
`/workers` onto the same origin, so it is the only configuration in which the
browser talks to one host — and two of the six defects below exist only there.

| spec | tests | covers |
| --- | ---: | --- |
| `shell.spec.ts` | 17 | every route, the sider, dark mode, collapse-and-reload, and each route reached by *pasting* it as well as by navigating to it |
| `explorer.spec.ts` | 31 | paging, server-side sorting, free text, the facet menus, the record drawer and its three tabs, the permalink |
| `pipeline.spec.ts` | 23 | the wiring, the worker runner, the analyse modal, the prompt editor's edit/save/discard/reset cycle |
| `record-page.spec.ts` | 15 | the seven panels in pipeline order, the service behind each, the calls and JSON tabs, a failed service shown where its text would have been |
| `advanced-search.spec.ts` | 13 | building a rule, the draft contract, the live preview count, the condition strip, Clear, nested groups |
| `saved-searches.spec.ts` | 11 | the whole lifecycle in one serial file, cleaning up after itself |
| `statistics.spec.ts` | 11 | the four headline numbers, one row per service, median/p95/max, recent failures |
| `export.spec.ts` | 7 | the download itself: format, file name, BOM, and that it carries the question on screen rather than the page |
| `dashboard.spec.ts` | 12 | the five tiles, the six charts and their accessible labels, every range preset, the drill-down into a narrowed explorer |
| `responsive.spec.ts` | 7 | the same screens on a Pixel 7, with no horizontal page scroll |

**The fixture is the point.** `tests/e2e/fixtures.ts` fails any test whose page
threw or logged a console error, with an opt-in allowance for the two screens
whose job is to render a failure. The bug this work started from was a console
error and a blank screen — a test asserting only "the heading is visible" would
have passed on a page that had already thrown.

### Performance — 19 tests, `tests/perf/test_performance.py`

Medians of seven runs, after a warm-up: the first request to a Flask process
pays for imports and the first query on a cold pool pays for a handshake, and
neither is what a reader experiences on the tenth search.

Measured on this machine, 120 records:

```
[perf] search, 25 rows              median=  10.9ms  p95=  58.1ms   budget=400ms
[perf] search + facets              median=  14.6ms  p95=  14.8ms   budget=700ms
[perf] search, free text            median=  16.1ms  p95=  18.6ms   budget=400ms
[perf] search, 200 rows             median=  33.1ms  p95=  77.8ms   budget=800ms
[perf] record detail                median=   4.2ms  p95=   4.4ms   budget=300ms
[perf] related records              median=   4.1ms  p95=   4.7ms   budget=600ms
[perf] dashboard, 30 days           median=   9.5ms  p95=  11.0ms   budget=1200ms
[perf] statistics, 30 days          median=   6.2ms  p95=   7.3ms   budget=1200ms
[perf] meta                         median=   1.0ms                 budget=200ms
[perf] health                       median=   2.6ms                 budget=200ms
[perf] pipeline config              median=   0.9ms                 budget=200ms
[perf] export csv, whole corpus     median=  43.7ms                 budget=2500ms
[perf] one mocked worker            median=  52.4ms                 budget=1500ms
[perf] whole pipeline, mocked       median= 356.3ms                 budget=5000ms

[perf] page 1 = 7.7ms,  page 12 = 8.3ms          (OFFSET does not degrade)
[perf] one detail = 3.8ms, ten in sequence = 37ms (no N+1 behind the children)
[perf] export first byte = 3.4ms, complete = 40ms (it is streamed, not assembled)
```

The budgets are an order of magnitude above the measurements on purpose. A test
that fails when somebody starts a build elsewhere is a test people delete; what
these catch is the class of regression that costs 10×, not 20% — a query that
stopped using an index, a facet computed per row, an N+1 behind a detail page.

### Load — 12 tests, `tests/perf/test_load.py`

`tests/support/loadgen.py` is 90 lines of threads and a histogram, deliberately
not a framework: a dependency that has to be installed first is a suite that
stops being run. Threads rather than asyncio because the thing under test is a
synchronous Flask app behind a thread pool.

```
[load] search x16      567 reqs / 5.1s   110 req/s  median=148.5ms p99=211.0ms  fail=0.0%
[load] search x24      567 reqs / 5.2s   109 req/s  median=220.7ms p99=289.4ms  fail=0.0%
[load] dashboard x12  1318 reqs / 5.0s   262 req/s  median= 45.3ms p99= 76.0ms  fail=0.0%
[load] mixed x16      1393 reqs / 5.0s   277 req/s  median= 52.7ms p99=135.7ms  fail=0.0%
[load] submit x8        57 reqs / 3.0s    19 req/s  median=  8.7ms p99= 12.4ms  fail=0.0%
[load] export x4        62 reqs / 4.1s    15 req/s  median=263.5ms p99=331.0ms  fail=0.0%
[load] health under load (while 8 threads hammer /statistics)  p95=36.6ms  fail=0.0%

[load] search @120   median=34.5ms      10x the corpus, and the median moves 8%
[load] search @1200  median=37.1ms
[load] one page of 1,200 answered in 28.6ms
```

What the thresholds assert is *shape*, not speed:

* **nothing fails.** 24 concurrent searchers against a pool of 5 with 10
  overflow queue rather than get a 503 — a reader must never be told "the
  records database is unavailable" because somebody else was searching.
* **latency degrades proportionally.** 11ms at one client, 148ms at sixteen, on
  a single Flask process: linear, not a cliff. A cliff is a lock held across a
  query.
* **the tail stays near the median.** p99 within 30× of the median; a p99 far
  past it is a queue, not slow SQL.
* **a cheap call survives an expensive one.** `/client/health` is polled by every
  open tab; it keeps a 36ms p95 while eight threads hammer the 90-day statistics.
* **ten times the data costs ~8%.** The corpus is re-seeded at 1,200 and put back
  at 120 afterwards.

---

## What it found

Six defects. Five fixed, one pinned.

### 1. A latent deadlock in the database bootstrap — fixed

`client/db.py` built its engine, its sessionmaker and its schema under a plain
`threading.Lock`, and two of those three call `engine()` **while already holding
it**. `engine()` takes the same non-reentrant lock, and the thread hangs for
ever.

It is invisible today only because `main.py` calls `available()` at boot, which
fills `_engine` so every later re-entry short-circuits before the lock. Any
process that reaches `create_schema()` or `session_scope()` first — which is
exactly what `store.save_record()` does — would stop dead, and a Kafka worker
stopping dead is silent.

Reproduced before fixing: `create_schema()` on a cold module never returned.
`_lock` is now an `RLock`, and it raises the connection error it should.

*Found by:* the existing suite's `test_a_dead_database_costs_the_row_not_the_record`,
which had been timing out at 30s rather than failing.

### 2. XLSX export was advertised and impossible — fixed

`/client/meta` published `["csv", "json", "xlsx"]`, the Export menu was built
from it, and **openpyxl was never in `requirements.txt`** — the import guard in
`export.py` even carried `# pragma: no cover - dependency is declared`. Every
XLSX export answered 400 "XLSX export is unavailable on this deployment".

Both halves fixed: the dependency is declared, and the advertised list is now
filtered by what actually imports, so a deployment that drops it shows an honest
menu rather than a broken button.

*Now covered by:* `test_every_advertised_format_can_actually_be_produced`
(integration) and `an XLSX export arrives as a workbook` (E2E).

### 3. A client mistake answered 500 — fixed

`POST /client/records/export` parsed the format, the columns and the condition
tree **before** its error guard, so `{"format": "pdf"}` produced
`{"message": "Internal Server Error"}` instead of a 400 naming what would work.
All three are client mistakes; they are inside the guard now.

*Now covered by:* three tests in `test_api_exports_and_meta.py`.

### 4. The Pipeline page 404'd when it was reloaded — fixed

nginx routed `^/(client|pipeline|workers|swagger\.json)` to the API, and that
regex matched the bare `/pipeline` — which is not an API path, it is a *client
route*. The page worked when it was navigated to (React Router never leaves the
browser) and answered a JSON 404 the moment anybody reloaded it, pasted the link
or opened a bookmark.

Every real API path has a segment after the namespace, so the match now requires
the slash and `/swagger.json` is anchored on its own.

*Found by:* the E2E suite visiting each route directly as well as navigating to
it. *Now covered by:* `deep links › /pipeline survives a reload`.

### 5. The facet menus were single-select in practice — fixed

`facets_for` promised counts "under the *other* filters currently applied" and
computed them from the fully filtered statement instead. Choosing NEGATIVE
removed POSITIVE and NEUTRAL from the menu, so the multi-select could only ever
hold one value and "NEGATIVE or POSITIVE" was reachable only by hand-editing the
URL.

Each facet is now counted with its own filter lifted and every other narrowing —
including the advanced condition — still applied. The *status* menu still
narrows to the records the sentiment filter left, which is the half that was
always right.

*Now covered by:* `a facet keeps offering the values not yet chosen`,
`every other facet still narrows with the question`, and the E2E
`the menu keeps offering the sentiments not yet chosen`.

### 6. Two smaller ones — fixed

* **The video's name was drawn twice.** `ResultsTable` unshifts a fixed,
  always-openable "Video" column *and* mapped `name` from the declared columns,
  so the table had two headings both called Video. `name` is dropped from the
  mapped set and the fixed column took over its sorter — the first attempt at
  this removed the ability to sort by name, which the E2E suite caught
  immediately.
* **An unhandled rejection on every failed form validation.** Both modals called
  `form.validateFields().then(...)` with no `.catch`, so pressing Submit on an
  empty required field logged an uncaught error for something the form had
  already pointed at on screen.

### And the one that started this

`crypto.randomUUID` is only defined in a **secure context** — HTTPS or
`localhost`. `queryTree.ts` called it unguarded, and `emptyTree()` runs while
the Explorer renders, so on `http://<host>:5697` the throw happened during
render and React unmounted the tree: the whole screen went blank. One
`randomId()` now backs both call sites, falling back to `getRandomValues`.

---

## Pinned, not fixed

Behaviours the suite now documents rather than changes. Each is a judgement
call, and the test says so in its name.

**"Save as…" also applies the draft.** The advanced drawer promises that
"nothing runs until you say so", and closing it does leave the table untouched —
but pressing **Save as…** sets the page's condition as well as saving it. That
is what makes the count in the save dialog describe the thing being saved, so it
is coherent; it is just not what the sentence above it implies. Pinned by
`an advanced condition can be saved from the drawer without running it`.

**An undeclared filter parameter is ignored.** `?no_such_column=x` narrows
nothing and does not fail, because the same argument bag carries `page`, `sort`
and whatever else a URL accumulated — refusing an unrecognised key would make a
pasted link a 400. The cost is that a *misspelt* filter silently returns the
unfiltered table, which is why the field catalogue is published and the frontend
builds its controls from it.

**`?mocked=1` is a 400 while `?mocked__eq=1` is accepted.** The bare filter
demands the word `true` or `false`; the explicit operator runs the value through
`_typed`, which also takes 1/yes/on. The frontend only ever sends the words, and
a filter that refuses what it cannot interpret is the safer of the two.

**`write_to` trusts its caller about the format.** An unknown format falls
through to CSV. Unreachable from HTTP — every endpoint runs `parse_format` first
— but worth a test so that a second caller finds a decision rather than a
surprise.

**The builder prettifies enum labels.** The facet menu says `NEGATIVE`, the
condition builder says `Negative`. Both send `NEGATIVE`.

---

## Four stale assertions in the suite that shipped

The suite was 68 passing / 4 failing before this work, and three of the four
were the tests being wrong about the application:

* **the sentiment case.** The mock answers `NEGATIVE`, which is what the record
  carries, what the facet menu offers and what every filter compares against.
  Two tests asserted the lowercase form, and a third did the same over Kafka.
* **the CSV BOM.** `csv_lines` opens with one on purpose, so Excel on Windows
  does not read the file as the local codepage. The export test read it as part
  of the header.
* **one path, two ids.** A run is named after the video file so that
  re-submitting one *replaces* its record — the documented contract of
  `publish_video`. The integration test asserted the opposite. It now asserts
  the real contract, and that an explicit id is what keeps both answers.

The fourth was defect #1 above.

---

## Things worth knowing before you add to this

**Test isolation bit once.** The integration suite needs the database on
in-process to seed; `Config` is a class of module-level values, so turning it on
in a session fixture turned it on for every test that ran afterwards — two unit
tests then read the *stored* prompt instead of the shipped file, and failed only
when the whole suite ran in one go. Seeding now happens inside a context manager
that puts the switch back. If you need in-process database access in a test, use
the `reseed` fixture or `_database_on()`; do not flip `Config` yourself.

**Run ids must not start with `qa-`.** The seeded corpus owns that prefix and
`seeded_only` filters on it. The pipeline integration tests use `probe-` for
exactly this reason — a submitted video named `qa-run-…` lands inside the corpus
and changes every total the records suite asserts.

**AntD's DOM has three traps**, all of which are handled in
`tests/e2e/fixtures.ts` and worth knowing before you write a selector:
a fixed column adds a hidden `tr.ant-table-measure-row`, so use `rows(page)`;
`getByLabel` matches two nodes for a Select (the root and its inner input), so
use `facet(page, …)`; and an icon inside a button carries its own `aria-label`,
so address buttons by role and exact name.

**Give the E2E suite an idle stack.** It passes 147/147 consistently on its
own, in about 45 seconds. Started immediately after the Python suite — while
the seven workers are still draining the load test's submissions — one run
reported 146. Nothing failed; the browser suite simply shares a Flask process
with a backlog. Run it first, or give the pipeline a minute.

**The E2E suite leaves the corpus behind.** That is deliberate — it makes the
next run immediate. `python tests/support/seed.py clear` removes it.

**A saturated run can leave stragglers.** Submitting a video answers in 9ms and
leaves seven workers busy *after* the response, so the burst test's records
arrive long after the requests do. It submits under a run-unique prefix, counts
what it handed out, and sweeps until it has removed that many or 180 seconds
pass — and under a full run, with the app container serving everything else, it
can still hit the deadline. The burst is capped at 50 for this reason: fifty
concurrent submissions prove what the test is about (a shared producer under
contention accepts every one) as well as a thousand would, and the cleanup
finishes. If anything is left over:

```bash
python tests/support/seed.py clear --prefix load-
python tests/support/seed.py clear --prefix probe-
python tests/support/seed.py clear --prefix it-
```

Nothing asserts against those prefixes, so stragglers are untidy rather than
wrong — but they are records in a corpus somebody may be looking at.

---

## What is not covered

Named so that nobody mistakes a green suite for more than it is.

* **The five AI services themselves.** Every suite here runs with
  `MOCK_WORKER_*=True`. The mocks are checked against the shape the workers read
  (`test_mock_answers.py`), and one live call to `:8821` was made by hand while
  debugging — but no test asserts anything about what a real model returns, and
  none should: that is the services' own suite.
* **Kafka failure modes.** The integration test publishes and waits for the
  record. It does not kill a broker mid-run, fill a partition, or exercise the
  DLQ.
* **Concurrency between the pipeline and the reader.** Nothing asserts what a
  search sees while W7 is writing the row it is about to return.
* **Anything about who is asking.** The app has no authentication; "owner" on a
  saved search is a label, not a principal, and the suite treats it as one.
* **Browsers other than Chromium.** The config has one desktop project and one
  Pixel 7; Firefox and WebKit would install and run, and have not been.
