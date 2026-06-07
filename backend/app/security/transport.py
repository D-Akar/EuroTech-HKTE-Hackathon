"""Transport-security middleware (PDPO DPP4 / GDPR Art.32).

TLS itself is terminated by the deployment platform / reverse proxy; this layer
*enforces its use* and hardens responses:

- ``force_https``: redirect any plaintext HTTP request to HTTPS (honours the
  ``X-Forwarded-Proto`` header set by proxies), and emit **HSTS**.
- ``security_headers``: defence-in-depth response headers on every response.

Both are config-gated. ``force_https`` is OFF by default (local dev is HTTP);
``security_headers`` is ON by default since the headers are harmless over HTTP.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from ..config import settings

_HSTS = "max-age=63072000; includeSubDomains; preload"
_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.split(",")[0].strip() == "https"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Redirect plaintext HTTP -> HTTPS when enforced (skip health checks).
        if settings.force_https and not _is_https(request) and request.url.path != "/health":
            https_url = request.url.replace(scheme="https")
            return RedirectResponse(str(https_url), status_code=308)

        response = await call_next(request)

        if settings.security_headers:
            for k, v in _HEADERS.items():
                response.headers.setdefault(k, v)
        if settings.force_https:
            response.headers.setdefault("Strict-Transport-Security", _HSTS)
        return response
