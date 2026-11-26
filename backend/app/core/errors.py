"""Uniform error responses and request plumbing (A02, A10).

- Every response gets a fresh X-Request-ID (inbound values are ignored).
- Unhandled exceptions → generic 500 with the request ID; the stack trace goes only
  to the server log.
- Validation errors list fields and messages but never echo the submitted input.
- API responses are `Cache-Control: no-store`.
- Unsafe API requests with a body must be JSON (or multipart on upload routes), which
  blocks cross-site HTML form posts before any CSRF token is involved.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .logging import request_id_var

log = logging.getLogger("app")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
MULTIPART_PATH_SUFFIXES: tuple[str, ...] = ()


def _error(status: int, code: str, **extra) -> JSONResponse:
    body = {"error": code, "request_id": request_id_var.get(), **extra}
    return JSONResponse(body, status_code=status)


class RequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            if request.method in UNSAFE and request.url.path.startswith("/api/"):
                has_body = request.headers.get("content-length", "0") != "0" or "transfer-encoding" in request.headers
                ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
                multipart_ok = ctype == "multipart/form-data" and request.url.path.endswith(MULTIPART_PATH_SUFFIXES)
                if has_body and ctype != "application/json" and not multipart_ok:
                    response: Response = _error(415, "unsupported_media_type")
                    response.headers["X-Request-ID"] = rid
                    return response
            response = await call_next(request)
        except Exception:  # pragma: no cover - safety net; handlers below normally catch
            log.exception("unhandled_error")
            response = _error(500, "internal_error")
        response.headers["X-Request-ID"] = rid
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        log.info("request", extra={"fields": {
            "method": request.method, "path": request.url.path, "status": response.status_code,
            "ms": round((time.perf_counter() - start) * 1000, 1),
        }})
        request_id_var.reset(token)
        return response


def install(app: FastAPI) -> None:
    app.add_middleware(RequestMiddleware)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            extra = {k: v for k, v in exc.detail.items() if k != "error"}
            resp = _error(exc.status_code, str(exc.detail.get("error", "error")), **extra)
        else:
            # Starlette's own 404/405 carry a human phrase; normalise to codes.
            code = exc.detail if isinstance(exc.detail, str) and exc.detail.islower() else {
                404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "error")
            resp = _error(exc.status_code, code)
        if exc.headers:
            resp.headers.update(exc.headers)
        return resp

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", "invalid")}
            for e in exc.errors()
        ]
        return _error(422, "validation_error", fields=fields)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", exc_info=exc)
        return _error(500, "internal_error")
