"""Optional HTTP API key. Empty DEVICE_AGENT_HTTP_API_KEY keeps the local demo open."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from terminal_agent.config import Settings

_PUBLIC_PREFIXES = (
    "/api/v1/health",
    "/api/v1/meta",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _is_public(path: str) -> bool:
    if path == "/" or not path.startswith("/api/"):
        return True
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _PUBLIC_PREFIXES)


def _provided_key(request: Request) -> str:
    header = request.headers.get("x-api-key") or ""
    auth = request.headers.get("authorization") or ""
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    query = request.query_params.get("api_key") or ""
    return header or bearer or query


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        expected = (self.settings.http_api_key or "").strip()
        if not expected or request.method == "OPTIONS" or _is_public(request.url.path):
            return await call_next(request)
        if _provided_key(request) != expected:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)
