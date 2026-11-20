"""Bounded read-only Census fetch retries and sanitized refresh evidence."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY = 30.0


def retry_delay(error: Exception, attempt: int, *, now: datetime | None = None) -> float | None:
    """Return a bounded delay, or decline rather than violate a long Retry-After."""
    delay = float(2 ** (attempt - 1))
    if isinstance(error, HTTPError) and error.headers:
        value = error.headers.get("Retry-After")
        if value:
            try:
                if value.strip().isdigit():
                    hint = float(value.strip())
                else:
                    timestamp = parsedate_to_datetime(value)
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=UTC)
                    hint = max(0.0, (timestamp - (now or datetime.now(UTC))).total_seconds())
                delay = max(delay, hint)
            except (TypeError, ValueError, OverflowError):
                pass  # Invalid upstream hint does not disable the bounded backoff.
    return delay if delay <= MAX_RETRY_DELAY else None


def _transient(error: Exception) -> bool:
    if isinstance(error, HTTPError):
        return error.code in RETRYABLE_HTTP
    if isinstance(error, URLError):
        return not isinstance(error.reason, ssl.SSLCertVerificationError)
    return isinstance(error, (TimeoutError, ConnectionError))


def _record(event: dict) -> None:
    destination = os.environ.get("REFRESH_DIAGNOSTICS_FILE")
    if destination:
        with Path(destination).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": datetime.now(UTC).isoformat(), **event}) + "\n")


def read_with_retry(request, *, opener, label: str, timeout: int = 60) -> bytes:
    """Retry transport failures only; parsing/coverage validation stays fail-closed.

    Evidence contains request hashes, status and exception types—not URLs,
    response bodies, exception messages, headers or environment values.
    """
    url = request if isinstance(request, str) else request.full_url
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        event = {"dataset": label, "request_sha256": key, "attempt": attempt}
        try:
            with opener(request, timeout=timeout) as response:
                result = response.read()
        except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
            delay = retry_delay(error, attempt) if _transient(error) and attempt < MAX_ATTEMPTS else None
            _record({**event, "outcome": "retry" if delay is not None else "failed",
                     "error_type": type(error).__name__,
                     "http_status": error.code if isinstance(error, HTTPError) else None,
                     "retry_delay_seconds": delay})
            if delay is None:
                raise
            time.sleep(delay)
        else:
            _record({**event, "outcome": "success", "bytes": len(result)})
            return result
    raise AssertionError("Unreachable retry state")
