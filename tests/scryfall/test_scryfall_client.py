import json
from typing import Any

from pytest import MonkeyPatch

import config
from meta_morphis.scryfall.client import batch, fetch_batch, fetch_single


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload

def test_fetch_batch_success(monkeypatch: MonkeyPatch) -> None:
    def fake_post(
        method: str, 
        url: str,
        headers: Any,
        params: Any,
        json: Any, 
        timeout: int
    ) -> FakeResponse:
        assert method == "POST"
        assert url == config.URL_COLLECTION
        assert json == {"identifiers": [{"name": "Lightning Bolt"}]}
        return FakeResponse(200, {"data": "ok"})

    monkeypatch.setattr("requests.request", fake_post)

    result = fetch_batch(["Lightning Bolt"])
    assert result == {"data": "ok"}

def test_fetch_batch_failure(monkeypatch: MonkeyPatch) -> None:
    def fake_post(
        method: str,
        url: str,
        headers: Any,
        params: Any,
        json: Any, 
        timeout: int
    ) -> FakeResponse:
        return FakeResponse(500, {"something_happened": []})

    monkeypatch.setattr("requests.request", fake_post)

    monkeypatch.setattr("time.sleep", lambda x: None)


    result = fetch_batch(["Bolt"])
    assert result is None

def test_fetch_single_first_attempt_success(monkeypatch: MonkeyPatch) -> None:
    def fake_get(
        method: str,
        url: str, 
        headers: Any, 
        params: Any, 
        json: Any,
        timeout: int
    ) -> FakeResponse:
        assert method == "GET"
        assert params == {"exact": "Lightning Bolt"}
        return FakeResponse(200, {"name": "Lightning Bolt"})

    monkeypatch.setattr("requests.request", fake_get)

    result = fetch_single("Lightning Bolt")
    assert result == {"name": "Lightning Bolt"}

def test_fetch_single_second_attempt_success(monkeypatch: MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_get(
        method: str,
        url: str, 
        headers: Any, 
        params: Any, 
        json: Any,
        timeout: int
    ) -> FakeResponse:
        calls.append(1)
        if len(calls) == 1:
            return FakeResponse(500, {"error": []})
        assert method == "GET"
        assert params == {"fuzzy": "Lightning Bolt"}
        return FakeResponse(200, {"name": "Lightning Bolt"})

    monkeypatch.setattr("requests.request", fake_get)
    monkeypatch.setattr("time.sleep", lambda x: None)

    result = fetch_single("Lightning Bolt")
    assert result == {"name": "Lightning Bolt"}

def test_fetch_single_failure(monkeypatch: MonkeyPatch) -> None:
    def fake_get(
        method: str,
        url: str, 
        headers: Any, 
        params: Any, 
        json: Any,
        timeout: int
    ) -> FakeResponse:
        return FakeResponse(404, {"error": []})

    monkeypatch.setattr("requests.request", fake_get)

    monkeypatch.setattr("time.sleep", lambda x: None)

    result = fetch_single("Unknown Card")
    assert result is None

def test_batch() -> None:
    names = ["a", "b", "c", "d", "e"]
    result = batch(names, size=2)
    assert result == [["a", "b"], ["c", "d"], ["e"]]