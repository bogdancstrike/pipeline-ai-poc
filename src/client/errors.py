"""Domain error taxonomy and the handlers that turn it into HTTP.

Handlers must be installed on the *flask-restx Api* as well as the Flask app:
restx installs its own error handling inside `Resource.dispatch_request`, so an
exception raised in a generated endpoint never reaches `@app.errorhandler` and
would otherwise surface as an opaque 500.
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    code = "error"
    status_code = 500

    def __init__(self, message: str = "", *, details: dict[str, Any] | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body


class ValidationError(ApiError):
    code = "validation_error"
    status_code = 400


class UnauthorizedError(ApiError):
    """No usable credential. The UI answers this with the 401 page."""

    code = "unauthorized"
    status_code = 401


class ForbiddenError(ApiError):
    """Authenticated, but the role does not carry the permission."""

    code = "forbidden"
    status_code = 403


class NotFoundError(ApiError):
    code = "not_found"
    status_code = 404


class ConflictError(ApiError):
    code = "conflict"
    status_code = 409


class UnprocessableError(ApiError):
    """Shape is right, meaning is wrong — e.g. a wizard step that fails a rule."""

    code = "unprocessable"
    status_code = 422


class RateLimitedError(ApiError):
    code = "rate_limited"
    status_code = 429


class ServiceUnavailableError(ApiError):
    code = "service_unavailable"
    status_code = 503


def install_restx_error_handlers(api) -> None:
    @api.errorhandler(ApiError)
    def _handle_domain(err: ApiError):
        return err.to_dict(), err.status_code


def install_flask_error_handlers(app) -> None:
    from framework.commons.logger import logger as log

    @app.errorhandler(ApiError)
    def _handle_domain(err: ApiError):
        return err.to_dict(), err.status_code

    @app.errorhandler(Exception)
    def _handle_unexpected(err: Exception):
        from werkzeug.exceptions import HTTPException

        if isinstance(err, HTTPException):
            return {"error": err.name, "message": err.description}, err.code
        log.exception(f"unhandled error: {err}")
        return {"error": "internal_error", "message": "internal server error"}, 500
