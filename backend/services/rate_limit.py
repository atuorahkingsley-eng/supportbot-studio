"""Shared slowapi limiter — keyed by client IP."""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": (
                f"Too many requests — limit of {exc.detail} exceeded. "
                "Please wait a moment and try again."
            )
        },
        headers={"Retry-After": "60"},
    )
