"""
The client app — everything that serves the analysed records to a browser.

The pipeline (`src/workers`) produces records; this package is the read side.
W7 hands each finished record to `store.save_record()`, which writes it to
PostgreSQL, and the endpoints under `/client/...` search, aggregate and export
what accumulates there.

    db.py          engine, session scope, schema creation
    models.py      the five tables — records, entities, persons, calls, searches
    store.py       record (the pipeline's JSON) -> rows.  W7's only entry point
    errors.py      the error envelope every endpoint answers failures with
    pagination.py  page/size/sort, and the list envelope
    query.py       declarative filter/sort/search/facets over a FieldSet
    rules.py       the query-builder's nested AND/OR tree -> SQL, and -> text
    resources.py   the FieldSet of the records table: what the UI may ask about
    explorer.py    the record list, one record, and the CSV/JSON export
    dashboard.py   the KPI tiles and the charts
    statistics.py  per-AI-service call counts, latencies and failure rates
    saved_searches.py   a search somebody named, so it can be re-run
    endpoints.py   the HTTP layer, wired in maps/endpoint.json

Nothing in here imports a worker, and no worker imports anything here except
`store`. The read side can be down, or its database can be, without the
pipeline noticing.
"""
