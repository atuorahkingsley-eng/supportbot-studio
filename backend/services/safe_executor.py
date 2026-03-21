"""
Safe executor with built-in retry logic (Phase 4).
Wraps any async function call with auto-heal retry logic and error logging.
"""
import asyncio
import traceback as tb
from typing import Callable, Optional

from sqlalchemy.orm import Session

from backend.config import settings


async def safe_execute(
    func: Callable,
    error_type: str,
    bot_id: Optional[str] = None,
    db: Optional[Session] = None,
    endpoint: Optional[str] = None,
    **kwargs,
):
    """
    Wrap any async function with retry logic and error logging.

    Usage:
        result = await safe_execute(
            my_async_func,
            error_type="api_error",
            bot_id="bot_abc123",
            db=db,
            endpoint="/api/chat",
            arg1=value1,
            arg2=value2,
        )

    On max retries exhausted, re-raises the last exception.
    """
    max_retries = settings.max_heal_retries
    last_exc = None

    for attempt in range(max_retries + 1):
        try:
            return await func(**kwargs)

        except Exception as e:
            last_exc = e

            if attempt == max_retries:
                # All retries exhausted — log final failure and re-raise
                if db is not None:
                    _log_error(db, bot_id, error_type, e, endpoint, attempt + 1)
                raise

            # Log each failed attempt
            if db is not None:
                _log_error(db, bot_id, error_type, e, endpoint, attempt + 1)

            # Smart back-off: longer waits for rate limits
            msg_lower = str(e).lower()
            if "rate" in msg_lower or "overload" in msg_lower or "529" in msg_lower:
                wait = (attempt + 1) * 10   # 10s, 20s
            elif "timeout" in msg_lower or "connection" in msg_lower:
                wait = (attempt + 1) * 5    # 5s, 10s
            else:
                wait = (attempt + 1) * 2    # 2s, 4s

            await asyncio.sleep(wait)

    raise last_exc  # pragma: no cover


def _log_error(db: Session, bot_id, error_type: str, exc: Exception, endpoint: str, retry_count: int):
    """Log a transient error (non-fatal retry attempt) to ErrorLog."""
    try:
        from backend.database import ErrorLog
        error_log = ErrorLog(
            bot_id=bot_id,
            error_type=error_type,
            error_message=str(exc)[:1000],
            traceback=tb.format_exc()[:3000],
            endpoint=endpoint or f"safe_execute",
            retry_count=retry_count,
            status="healing",
        )
        db.add(error_log)
        db.commit()
    except Exception:
        pass  # Never let error logging crash the app
