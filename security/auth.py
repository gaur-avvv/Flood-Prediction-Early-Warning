"""API-key auth, scopes and sliding-window rate limiting (Sprint 0 / T-29).

Configuration (env):
  FLOOD_API_KEYS="keyA:predict:read,scan:read;keyB:admin"
      Semicolon-separated ``key:scope1,scope2`` entries. A key with no scopes
      gets ``predict:read`` only. ``admin`` implies every scope. Setting any
      key enables auth.
  FLOOD_AUTH_REQUIRED=true   Force auth on even with an empty key list.
  FLOOD_ENV=production       Startup refuses to run without keys (see main.py).
  FLOOD_RATE_LIMIT_PER_MINUTE=120        default bucket
  FLOOD_SCAN_RATE_LIMIT_PER_MINUTE=12    scan:read bucket (expensive endpoints)

Scopes per docs/06 §4: predict:read, scan:read, alerts:write, admin.
Public paths: /health, /ready, /docs, /redoc, /openapi.json.
"""

import logging
import os
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from utils.errors import error_body
from utils.request_id import get_request_id

logger = logging.getLogger(__name__)

ALL_SCOPES = ("predict:read", "scan:read", "alerts:write", "admin")

PUBLIC_PATHS = {
    "/",
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/docs/oauth2-redirect",
}

# path prefix -> required scope (first match wins)
ROUTE_SCOPES: Tuple[Tuple[str, str], ...] = (
    ("/predict", "predict:read"),
    ("/nowcast", "predict:read"),
    ("/hotspots", "scan:read"),
    ("/wards", "scan:read"),
    ("/email", "alerts:write"),
    ("/train", "admin"),
    ("/data/ingest", "admin"),
    ("/data/summary", "predict:read"),
)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def parse_api_keys(raw: str) -> Dict[str, List[str]]:
    keys: Dict[str, List[str]] = {}
    for entry in raw.replace("\n", ";").split(";"):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            key, scopes = entry.split(":", 1)
            parsed = [s.strip() for s in scopes.split(",") if s.strip()]
            unknown = [s for s in parsed if s not in ALL_SCOPES]
            if unknown:
                logger.warning(
                    "Ignoring unknown scopes %s for key …%s", unknown, key.strip()[-4:]
                )
            parsed = [s for s in parsed if s in ALL_SCOPES]
            keys[key.strip()] = parsed or ["predict:read"]
        else:
            keys[entry] = ["predict:read"]
    return {k: v for k, v in keys.items() if k}


def has_scope(granted: List[str], required: str) -> bool:
    return "admin" in granted or required in granted


def normalise_path(path: str) -> str:
    """Strip the /v1 prefix so rules match versioned and legacy paths alike."""
    if path == "/v1":
        return "/"
    if path.startswith("/v1/"):
        return path[3:]
    return path


def scope_for_path(path: str) -> Optional[str]:
    norm = normalise_path(path)
    if norm in PUBLIC_PATHS:
        return None
    for prefix, scope in ROUTE_SCOPES:
        if norm.startswith(prefix):
            return scope
    return None


class RateLimiter:
    """In-memory sliding-window limiter keyed by (identity, bucket)."""

    def __init__(self, window_seconds: float = 60.0):
        self.window = window_seconds
        self._hits: Dict[Tuple[str, str], deque] = {}
        self._lock = threading.Lock()

    def allow(self, identity: str, bucket: str, limit: int) -> Tuple[bool, float]:
        now = time.monotonic()
        key = (identity, bucket)
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and now - dq[0] > self.window:
                dq.popleft()
            if len(dq) >= limit:
                return False, max(1.0, self.window - (now - dq[0]))
            dq.append(now)
            if len(self._hits) > 50_000:  # memory guard
                self._hits.clear()
        return True, 0.0


class AuthConfig:
    def __init__(self):
        self.keys: Dict[str, List[str]] = parse_api_keys(os.getenv("FLOOD_API_KEYS", ""))
        self.enabled: bool = _env_bool("FLOOD_AUTH_REQUIRED") or bool(self.keys)
        self.production: bool = (
            os.getenv("FLOOD_ENV", "development").strip().lower() == "production"
        )
        self.default_rate: int = int(os.getenv("FLOOD_RATE_LIMIT_PER_MINUTE", "120"))
        self.scan_rate: int = int(os.getenv("FLOOD_SCAN_RATE_LIMIT_PER_MINUTE", "12"))


_config: Optional[AuthConfig] = None


def get_auth_config() -> AuthConfig:
    global _config
    if _config is None:
        _config = AuthConfig()
    return _config


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: Optional[AuthConfig] = None):
        super().__init__(app)
        self.config = config or get_auth_config()
        self.limiter = RateLimiter()
        self._warned = False

    async def dispatch(self, request: Request, call_next):
        norm = normalise_path(request.url.path)
        if norm in PUBLIC_PATHS or norm.startswith("/docs") or norm.startswith("/redoc"):
            return await call_next(request)

        scope = scope_for_path(request.url.path)
        if scope is None:  # unknown route → let it 404
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if self.config.enabled:
            if not api_key or api_key not in self.config.keys:
                return JSONResponse(
                    status_code=401,
                    content=error_body(
                        "unauthenticated",
                        "A valid API key is required (X-API-Key header).",
                        None,
                        get_request_id(request),
                    ),
                )
            if not has_scope(self.config.keys[api_key], scope):
                return JSONResponse(
                    status_code=403,
                    content=error_body(
                        "insufficient_scope",
                        f"Scope '{scope}' is required for this endpoint.",
                        {"required_scope": scope},
                        get_request_id(request),
                    ),
                )
            identity = api_key
        else:
            if not self._warned:
                logger.warning(
                    "API auth DISABLED (dev mode) – set FLOOD_API_KEYS to enable."
                )
                self._warned = True
            identity = api_key or (
                request.client.host if request.client else "anonymous"
            )

        bucket = "scan" if scope == "scan:read" else "default"
        limit = self.config.scan_rate if bucket == "scan" else self.config.default_rate
        allowed, retry_after = self.limiter.allow(identity, bucket, limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=error_body(
                    "rate_limited",
                    f"Rate limit exceeded ({limit} requests/minute for this bucket).",
                    {"bucket": bucket, "limit_per_minute": limit},
                    get_request_id(request),
                ),
                headers={"Retry-After": str(int(retry_after))},
            )
        return await call_next(request)
