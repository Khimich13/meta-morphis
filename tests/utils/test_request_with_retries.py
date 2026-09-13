import json
from typing import Any

from pytest import MonkeyPatch

from meta_morphis.utils.http import request_with_retries


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

    result = request_with_retries("GET", "http://fake", max_retries=3)
    assert result is None