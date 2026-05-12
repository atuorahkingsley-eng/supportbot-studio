"""Shared slowapi limiter — keyed by client IP, plus a per-(bot_id, ip) helper."""
import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


# ── Per-(bot_id, ip) sliding window ──────────────────────────────────────────
# slowapi's key_func runs sync before body parse, so it cannot read
# `data.bot_id` from a JSON body. The decorator stays IP-only as a first
# line; this helper layers a (bot_id, ip) check after body parse so:
#   - a NATted shared IP gets a fresh budget per tenant (no false positives
#     for legitimate users on the same IP visiting different bots);
#   - a tenant-targeted attacker on one bot can't drain the IP budget for
#     legitimate users hitting a different bot from the same IP.
# Per-process memory matches slowapi's default storage (no shared store
# across workers) — accepted trade-off for zero new dependencies.
#
# Memory bounding: _prune_buckets() removes entries whose window has expired,
# and enforces a hard cap of MAX_BUCKETS to prevent unbounded growth from
# unique-visitor accumulation over weeks of uptime.
_buckets: Dict[Tuple[str, str], Deque[float]] = {}
_buckets_lock = Lock()
_WINDOW_SECONDS = 60.0
_MAX_BUCKETS = 10_000


def _prune_buckets() -> None:
    """Remove expired rate limit buckets to bound memory growth."""
    now = time.time()
    expired = [k for k, v in _buckets.items() if v and v[-1] < now - _WINDOW_SECONDS]
    for k in expired:
        del _buckets[k]
    if len(_buckets) > _MAX_BUCKETS:
        oldest = sorted(
            _buckets.items(),
            key=lambda x: x[1][-1] if x[1] else 0,
        )[:len(_buckets) - _MAX_BUCKETS]
        for k, _ in oldest:
            del _buckets[k]


def check_bot_id_rate_limit(bot_id: str, ip: str, max_per_minute: int) -> bool:
    """Return True if the (bot_id, ip) request is allowed, False if over cap.

    Sliding window over the last 60 seconds. Caller is responsible for
    raising HTTP 429 when this returns False — keeping the helper itself
    framework-free so it stays unit-testable.
    """
    key = (bot_id or "", ip or "")
    now = time.time()
    cutoff = now - _WINDOW_SECONDS
    with _buckets_lock:
        _prune_buckets()
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = deque()
            _buckets[key] = bucket
        # Drop expired entries from the left edge.
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_per_minute:
            return False
        bucket.append(now)
        return True


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
