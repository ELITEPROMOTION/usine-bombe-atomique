"""Middleware de security headers (Starlette).

Ajoute :
- HSTS (max-age 1 an)
- CSP (default-src 'self' — strict)
- X-Frame-Options DENY
- X-Content-Type-Options nosniff
- Referrer-Policy strict-origin-when-cross-origin
- Permissions-Policy basique (no camera/mic/geolocation par defaut)

Usage cote `main.py` :
    app.add_middleware(SecurityHeadersMiddleware)

Customisable via parametres (CSP plus laxe pour /docs Swagger, etc.).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

DEFAULT_HSTS: Final[str] = "max-age=31536000; includeSubDomains"

# CSP minimaliste — application JSON-only par defaut. Customiser pour
# servir une UI HTML.
DEFAULT_CSP: Final[str] = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https://api.stripe.com https://api.anthropic.com "
    "https://api.perplexity.ai; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

DEFAULT_PERMISSIONS_POLICY: Final[str] = (
    "camera=(), microphone=(), geolocation=(), payment=()"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute les headers de securite OWASP standard a chaque reponse."""

    def __init__(
        self,
        app,
        *,
        hsts: str = DEFAULT_HSTS,
        csp: str = DEFAULT_CSP,
        permissions_policy: str = DEFAULT_PERMISSIONS_POLICY,
        skip_paths: tuple[str, ...] = ("/docs", "/redoc", "/openapi.json"),
    ) -> None:
        super().__init__(app)
        self._hsts = hsts
        self._csp = csp
        self._permissions = permissions_policy
        self._skip_paths = skip_paths

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        # Pour les endpoints de doc Swagger, on assouplit (sinon /docs est cassee).
        skip = any(path.startswith(p) for p in self._skip_paths)
        if not skip:
            response.headers.setdefault("Strict-Transport-Security", self._hsts)
            response.headers.setdefault("Content-Security-Policy", self._csp)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin",
        )
        response.headers.setdefault("Permissions-Policy", self._permissions)
        return response
