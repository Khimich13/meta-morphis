import logging
import math
import time
from typing import Any
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

# Persists across separate calls (not just retries within one call), so
# min_delay actually paces consecutive requests. A caller like
# _process_batch_request makes many separate top-level calls to
# request_with_retries in a loop - a function-local timestamp resets on
# every one of them and can never enforce spacing between them.
# Read from time.monotonic(), not time.time(): the wall clock can be set
# back mid-run, and a gap measured across that correction would turn
# into a sleep as long as the correction itself.
_last_request_time = 0.0


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
    max_retry_after: float = 60.0,
    default_retry_after: float | None = None
) ->  str | None:

    global _last_request_time
    used_retry_after = False
    # Just the server's name, for the messages below
    host = urlsplit(url).netloc

    for attempt in range(max_retries):
        if used_retry_after:
            used_retry_after = False
        else:
            now = time.monotonic()
            since_last = now - _last_request_time
            if since_last < min_delay:
                time.sleep(min_delay - since_last)

        _last_request_time = time.monotonic()

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
            delay = backoff_base * (2 ** attempt)
            log.warning(f"Network error reaching {host} ({e}), retrying in {delay:g} s")
            time.sleep(delay)
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
            if delay is None and default_retry_after is not None:
                # Some APIs lock you out for a fixed time after a 429
                # without saying so in Retry-After (Scryfall: 30s) -
                # retrying on the short backoff would land inside that
                # lockout and only count as more overload.
                delay = max(0.0, min(default_retry_after, max_retry_after))
            if delay is None:
                delay = backoff_base * (2 ** attempt)

            if attempt + 1 == max_retries:
                raise RequestUnavailable(f"rate limited after {max_retries} attempts")

            # Worth seeing: a client that keeps getting 429s can be blocked
            log.warning(f"Rate limited by {host}, waiting {delay:g} s")
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
            log.warning(f"Server error {status} from {host}, retrying in {delay:g} s")
            time.sleep(delay)
            continue

        # --- Success path ---
        if status == 200:
            return response.text

        # Unexpected status codes - not a clean "doesn't exist", don't guess
        raise RequestUnavailable(f"unexpected status {status}")

    raise RequestUnavailable(f"request could not be completed within {max_retries} attempts")