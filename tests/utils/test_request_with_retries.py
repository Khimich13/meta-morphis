from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis.utils.http import RequestUnavailable, request_with_retries


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        text: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code: int = status_code
        self.text = text
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return {"text": self.text}


def test_request_success(monkeypatch: MonkeyPatch) -> None:
    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        return FakeResponse(200, "OK")

    monkeypatch.setattr("requests.request", fake_request)
    result = request_with_retries("GET", "http://fake")
    assert result == "OK"

# the pacing timestamp used to be a function local, reset to 0.0 on every call,
# so min_delay could never be enforced between separate top-level calls
def test_request_with_retries_paces_between_separate_calls(monkeypatch: MonkeyPatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr("time.time", lambda: clock[0])

    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        return FakeResponse(200, "OK")

    monkeypatch.setattr("requests.request", fake_request)

    request_with_retries("GET", "http://fake", min_delay=0.2)
    # Almost no real time passes before the next call, matching two
    # back-to-back fetch_single() calls in a loop.
    clock[0] += 0.01
    request_with_retries("GET", "http://fake", min_delay=0.2)

    assert slept == [pytest.approx(0.19)]

def test_request_retry_then_success(monkeypatch: MonkeyPatch) -> None:
    """Should retry on non-200 and succeed on next attempt."""
    calls: list[int] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        calls.append(1)
        if len(calls) == 1:
            return FakeResponse(500, "fail")
        return FakeResponse(200, "OK")

    monkeypatch.setattr("requests.request", fake_request)
    monkeypatch.setattr("time.sleep", lambda x: None)

    result = request_with_retries("GET", "http://fake", max_retries=3)
    assert result == "OK"
    assert len(calls) == 2

def test_request_retry_after(monkeypatch: MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        calls.append(1)
        if len(calls) == 1:
            return FakeResponse(429, "rate", headers={"Retry-After": "1"})
        return FakeResponse(200, "OK")

    monkeypatch.setattr("requests.request", fake_request)

    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda x: slept.append(x))

    result = request_with_retries("GET", "http://fake", max_retries=3)
    assert result == "OK"
    assert slept == [1.0]

# A negative Retry-After (e.g. from clock skew on the server)
def test_request_retry_after_negative_value_is_clamped(monkeypatch: MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        calls.append(1)
        if len(calls) == 1:
            return FakeResponse(429, "rate", headers={"Retry-After": "-5"})
        return FakeResponse(200, "OK")

    monkeypatch.setattr("requests.request", fake_request)

    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda x: slept.append(x))

    result = request_with_retries("GET", "http://fake", max_retries=3)
    assert result == "OK"
    assert slept == [0.0]

# An absurdly large Retry-After (e.g. "3600") used to block for the full
# duration on every retry, even on a call with a 5s timeout - it must be
# capped at max_retry_after instead of honoured verbatim.
def test_request_retry_after_huge_value_is_capped(monkeypatch: MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        calls.append(1)
        if len(calls) == 1:
            return FakeResponse(429, "rate", headers={"Retry-After": "3600"})
        return FakeResponse(200, "OK")

    monkeypatch.setattr("requests.request", fake_request)

    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda x: slept.append(x))

    result = request_with_retries("GET", "http://fake", max_retries=3, max_retry_after=60.0)
    assert result == "OK"
    assert slept == [60.0]

# "inf"/"nan" parse successfully as floats but aren't usable delays -
# time.sleep(inf) raises OverflowError and time.sleep(nan) raises
# ValueError, so these must fall back to exponential backoff instead.
def test_request_retry_after_non_finite_falls_back_to_backoff(monkeypatch: MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        calls.append(1)
        if len(calls) == 1:
            return FakeResponse(429, "rate", headers={"Retry-After": "inf"})
        return FakeResponse(200, "OK")

    monkeypatch.setattr("requests.request", fake_request)

    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda x: slept.append(x))

    result = request_with_retries("GET", "http://fake", max_retries=3, backoff_base=0.5)
    assert result == "OK"
    assert slept == [0.5]

def test_request_failure(monkeypatch: MonkeyPatch) -> None:
    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        return FakeResponse(500, "fail")

    monkeypatch.setattr("requests.request", fake_request)
    monkeypatch.setattr("time.sleep", lambda x: None)

    with pytest.raises(RequestUnavailable):
        request_with_retries("GET", "http://fake", max_retries=3)

# A clean 404/422 means "this genuinely doesn't exist" and must return None immediately
@pytest.mark.parametrize("status", [404, 422])
def test_request_not_found_returns_none_without_retrying(monkeypatch: MonkeyPatch, status: int) -> None:
    calls: list[int] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        calls.append(1)
        return FakeResponse(status, "not found")

    monkeypatch.setattr("requests.request", fake_request)
    monkeypatch.setattr("time.sleep", lambda x: None)

    result = request_with_retries("GET", "http://fake", max_retries=3)
    assert result is None
    assert len(calls) == 1

def test_request_network_error_raises_after_retries(monkeypatch: MonkeyPatch) -> None:
    import requests

    def fake_request(*args: Any, **kwargs: Any) -> FakeResponse:
        raise requests.ConnectionError("boom")

    monkeypatch.setattr("requests.request", fake_request)
    monkeypatch.setattr("time.sleep", lambda x: None)

    with pytest.raises(RequestUnavailable):
        request_with_retries("GET", "http://fake", max_retries=3)

# min_delay=0.0 keeps pacing out of `slept` - with sleep mocked no real time
# passes between attempts, so pacing would otherwise add its own sleeps.
def test_request_network_error_backs_off_exponentially(monkeypatch: MonkeyPatch) -> None:
    import requests

    def fake_request(*args: Any, **kwargs: Any) -> FakeResponse:
        raise requests.ConnectionError("boom")

    monkeypatch.setattr("requests.request", fake_request)

    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda x: slept.append(x))

    with pytest.raises(RequestUnavailable):
        request_with_retries("GET", "http://fake", max_retries=3, min_delay=0.0, backoff_base=0.5)

    # No sleep after the last attempt - it raises instead
    assert slept == [0.5, 1.0]

def test_request_server_error_backs_off_exponentially(monkeypatch: MonkeyPatch) -> None:
    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        return FakeResponse(503, "unavailable")

    monkeypatch.setattr("requests.request", fake_request)

    slept: list[float] = []
    monkeypatch.setattr("time.sleep", lambda x: slept.append(x))

    with pytest.raises(RequestUnavailable):
        request_with_retries("GET", "http://fake", max_retries=3, min_delay=0.0, backoff_base=0.5)

    assert slept == [0.5, 1.0]

def test_request_rate_limit_exhausted_raises(monkeypatch: MonkeyPatch) -> None:
    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        return FakeResponse(429, "rate", headers={"Retry-After": "0"})

    monkeypatch.setattr("requests.request", fake_request)
    monkeypatch.setattr("time.sleep", lambda x: None)

    with pytest.raises(RequestUnavailable):
        request_with_retries("GET", "http://fake", max_retries=3)

def test_request_unexpected_status_raises(monkeypatch: MonkeyPatch) -> None:
    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json: Any = None,
        timeout: float = 10
    ) -> FakeResponse:
        return FakeResponse(301, "moved")

    monkeypatch.setattr("requests.request", fake_request)

    with pytest.raises(RequestUnavailable):
        request_with_retries("GET", "http://fake", max_retries=3)