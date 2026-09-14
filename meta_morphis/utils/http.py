import time
from typing import Any

import requests


def request_with_retries(
    method: str,
    url: str, 
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    timeout: float = 5.0,
    max_retries: int = 3,
    min_delay: float = 0.2,
    backoff_base: float = 0.5
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

        if attempt > 0 and params is not None and "exact" in params:
            params = params.copy()
            params["fuzzy"] = params["exact"]
            del params["exact"]

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                timeout=timeout,
            )
        except requests.RequestException:
            # Network-level failure → retry
            if attempt + 1 == max_retries:
                return None
            time.sleep(backoff_base * (2 ** attempt))
            continue

        status = response.status_code

        # Immediate failures (no retries)
        if status in (404, 422):
            return None

        # Rate limiting (429)
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = backoff_base * (2 ** attempt)
            else:
                delay = backoff_base * (2 ** attempt)

            if attempt + 1 == max_retries:
                return None

            time.sleep(delay)
            used_retry_after = True
            continue

        # Server errors (5xx)
        if 500 <= status < 600:
            if attempt + 1 == max_retries:
                return None
            delay = backoff_base * (2 ** attempt)
            time.sleep(delay)
            continue

        # --- Success path ---
        if status == 200:
            try:
                return response.text
            except ValueError:
                # JSON decoding failure
                return None

        # Unexpected status codes
        return None

    return None