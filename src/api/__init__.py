"""
The HTTP layer — two front doors onto the same seven workers.

  pipeline_endpoints.py   POST /pipeline/analyze  — publish to Kafka, the
                          pipeline runs asynchronously across all seven workers
  worker_endpoints.py     POST /workers/{name}/run — run ONE worker here and
                          now, synchronously, and return what it produced

Endpoints are registered from `maps/endpoint.json`, which names the module and
the function for each route; Flask-RESTX builds the Swagger UI at
http://localhost:5000/ from the same file.

Handlers are called as `fn(app=..., operation=..., request=..., **path_params)`
and their return value is serialised by Flask-RESTX, so they return a plain
dict or a `(dict, status_code)` tuple — never a `flask.jsonify()` Response.
"""

from flask import request as flask_request


def json_body() -> dict:
    """The request body as a dict, or `{}`.

    `silent=True` turns a missing or malformed body into `{}` instead of an
    opaque werkzeug 400; `force=True` parses it without a JSON content-type.
    """
    payload = flask_request.get_json(force=True, silent=True)
    return payload if isinstance(payload, dict) else {}
