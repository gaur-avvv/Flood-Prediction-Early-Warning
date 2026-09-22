"""Request-ID middleware (Sprint 0 / T-01, contract AC-04).

Every response carries an ``X-Request-ID`` header. A client-supplied ID is
honoured (echoed back); otherwise a new ``req_<hex16>`` ID is minted.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_ID_HEADER = "X-Request-ID"


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:16]}"


def get_request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return rid if rid else new_request_id()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        request.state.request_id = rid
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
