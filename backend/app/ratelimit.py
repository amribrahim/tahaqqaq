"""A small in-memory sliding-window limiter, per client IP and bucket, protecting the free model quotas.
Behind Caddy the client address comes from X-Forwarded-For (the API port is bound to localhost only)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(request: Request, bucket: str, limit: int, window_s: float, lang: str = "ar") -> None:
    """Raise 429 when this client used more than `limit` calls of `bucket` in the last `window_s` seconds."""
    now = time.monotonic()
    key = (bucket, client_ip(request))
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            msg = ("طلبات كثيرة خلال وقت قصير. انتظر دقائق ثم حاول مرة أخرى." if lang == "ar"
                   else "Too many requests in a short time. Please wait a few minutes and try again.")
            raise HTTPException(429, {"code": "rate_limited", "message": msg})
        q.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
