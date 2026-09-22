"""Structured API error handling (Sprint 0 / T-01, contract AC-04).

Canonical error shape for every non-2xx response:

    {"error": {"code": "...", "message": "...", "details": ...},
     "request_id": "req_..."}

Error codes follow docs/06-API-CONTRACT-SPEC.md §5.
"""

import logging
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from utils.request_id import get_request_id

logger = logging.getLogger(__name__)

_STATUS_TO_CODE = {
    400: "validation_error",
    401: "unauthenticated",
    403: "insufficient_scope",
    404: "not_found",
    405: "method_not_allowed",
    409: "idempotency_conflict",
    413: "payload_too_large",
    422: "missing_covariates",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_unavailable",
    503: "service_unavailable",
    504: "upstream_timeout",
}


class APIError(HTTPException):
    """HTTPException carrying a machine-readable code and structured details."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
    ):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details


def error_body(
    code: str, message: str, details: Optional[Any], request_id: str
) -> dict:
    return {
        "error": {"code": code, "message": message, "details": details},
        "request_id": request_id,
    }


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.details, get_request_id(request)),
        headers=exc.headers,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = _STATUS_TO_CODE.get(exc.status_code, "internal_error")
    message = str(exc.detail)
    details: Optional[Any] = None
    if isinstance(exc.detail, dict):  # allow detail={"code": ..., "message": ...}
        code = exc.detail.get("code", code)
        message = exc.detail.get("message", code)
        details = exc.detail.get("details")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, details, get_request_id(request)),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {
            "loc": [str(p) for p in err.get("loc", [])],
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()[:25]
    ]
    return JSONResponse(
        status_code=400,  # contract: schema validation returns 400, not 422
        content=error_body(
            "validation_error",
            "Request validation failed.",
            details,
            get_request_id(request),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body(
            "internal_error",
            "An unexpected error occurred.",
            None,
            get_request_id(request),
        ),
    )
