import math
import time
from typing import Any

import requests


class RequestUnavailable(Exception):
    """Raised when a request could not be completed after retries -
    a network failure, exhausted rate-limit/server-error retries, or an
    unexpected status code.

    This is distinct from a clean 404/422, which means the resource
    genuinely doesn't exist and is signalled by returning None instead.
    Callers must not treat the two the same: a None result can be
    recorded as "this name doesn't exist", but a RequestUnavailable only
    means "we don't know" and should be retried later, not recorded as
    a permanent failure.
    """


def request_with_retries(
    method: str,
    url: str, 
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    timeout: float = 5.0,
    max_retries: int = 3,
    min_delay: float = 0.2,
    backoff_base: float = 0.5,
    max_retry_after: float = 60.0
) ->  str | None:

    last_attempt_time = 0.0
    used_retry_after = False

    for attempt in range(max_retries):
        if used_retry_after:
            used_retry_after = False
        else:
            now = time.time()
            since_last = now - last_attempt_time
            if since_last < min_delay:
                time.sleep(min_delay - since_last)

        last_attempt_time = time.time()

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                timeout=timeout,
            )
        except requests.RequestException as e:
            # Network-level failure → retry
            if attempt + 1 == max_retries:
                raise RequestUnavailable(
                    f"network error after {max_retries} attempts: {e}"
                ) from e
            time.sleep(backoff_base * (2 ** attempt))
            continue

        status = response.status_code

        # Immediate failures (no retries) - the resource genuinely doesn't exist
        if status in (404, 422):
            return None

        # Rate limiting (429)
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            delay = None
            if retry_after:
                try:
                    parsed = float(retry_after)
                    if math.isfinite(parsed):
                        # A server-supplied delay is honoured but clamped -
                        # a negative value (clock skew) or an absurdly
                        # large one must not turn into a negative sleep()
                        # (raises) or an hour-long block on a 5s-timeout call.
                        delay = max(0.0, min(parsed, max_retry_after))
                except ValueError:
                    pass
            if delay is None:
                delay = backoff_base * (2 ** attempt)

            if attempt + 1 == max_retries:
                raise RequestUnavailable(f"rate limited after {max_retries} attempts")

            time.sleep(delay)
            used_retry_after = True
            continue

        # Server errors (5xx)
        if 500 <= status < 600:
            if attempt + 1 == max_retries:
                raise RequestUnavailable(
                    f"server error {status} after {max_retries} attempts"
                )
            delay = backoff_base * (2 ** attempt)
            time.sleep(delay)
            continue

        # --- Success path ---
        if status == 200:
            return response.text

        # Unexpected status codes - not a clean "doesn't exist", don't guess
        raise RequestUnavailable(f"unexpected status {status}")

    raise RequestUnavailable(f"request could not be completed within {max_retries} attempts")