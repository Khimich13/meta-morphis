import json
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.scryfall.client import fetch_batch, fetch_single
from meta_morphis.utils.http import RequestUnavailable


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
        assert url == config.SCRYFALL_COLLECTION_URL
        assert json == {"identifiers": [{"name": "Lightning Bolt"}]}
        return FakeResponse(200, {"data": "ok"})

    monkeypatch.setattr("requests.request", fake_post)

    result = fetch_batch(["Lightning Bolt"])
    assert result == {"data": "ok"}

def test_fetch_batch_failure(monkeypatch: MonkeyPatch) -> None:
    # A 500 exhausting all retries means "couldn't complete the request",
    # not "these cards don't exist" - fetch_batch must let it propagate
    # rather than return None, so callers don't mistake a Scryfall outage
    # for a clean empty result.
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

    with pytest.raises(RequestUnavailable):
        fetch_batch(["Bolt"])

def test_fetch_batch_bad_200_response(monkeypatch: MonkeyPatch) -> None:
    # A 200 status doesn't guarantee a JSON body - e.g. a Cloudflare
    # interstitial or a truncated proxy response. request_with_retries
    # treats 200 as success and returns the raw text either way.
    def fake_post(
        method: str,
        url: str,
        headers: Any,
        params: Any,
        json: Any,
        timeout: int
    ) -> FakeResponse:
        response = FakeResponse(200, {})
        response.text = "<html>Just a moment...</html>"
        return response

    monkeypatch.setattr("requests.request", fake_post)

    with pytest.raises(RequestUnavailable):
        fetch_batch(["Lightning Bolt"])

def test_fetch_single_exact_success(monkeypatch: MonkeyPatch) -> None:
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

def test_fetch_single_fuzzy_success(monkeypatch: MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake_request_with_retries(
        method: str, url: str, headers: Any, params: Any, **kwargs: Any
    ) -> str | None:
        calls.append(params)
        if params == {"exact": "Lightning Bolt"}:
            return None
        assert params == {"fuzzy": "Lightning Bolt"}
        return json.dumps({"name": "Lightning Bolt"})

    monkeypatch.setattr(
        "meta_morphis.scryfall.client.request_with_retries",
        fake_request_with_retries
    )

    result = fetch_single("Lightning Bolt")
    assert result == {"name": "Lightning Bolt"}
    assert calls == [{"exact": "Lightning Bolt"}, {"fuzzy": "Lightning Bolt"}]

def test_fetch_single_exact_404_falls_back_to_fuzzy(monkeypatch: MonkeyPatch) -> None:
    def fake_get(
        method: str,
        url: str,
        headers: Any,
        params: Any,
        json: Any,
        timeout: int
    ) -> FakeResponse:
        if params == {"exact": "Lightnig Bolt"}:
            return FakeResponse(404, {"error": []})
        assert params == {"fuzzy": "Lightnig Bolt"}
        return FakeResponse(200, {"name": "Lightning Bolt"})

    monkeypatch.setattr("requests.request", fake_get)

    result = fetch_single("Lightnig Bolt")
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

# Returning None here used to read as "confirmed missing", which put a
# real card on the 7-day card_lookup_failures list
def test_fetch_single_bad_200_response(monkeypatch: MonkeyPatch) -> None:
    def fake_get(
        method: str,
        url: str,
        headers: Any,
        params: Any,
        json: Any,
        timeout: int
    ) -> FakeResponse:
        response = FakeResponse(200, {})
        response.text = "<html>Just a moment...</html>"
        return response

    monkeypatch.setattr("requests.request", fake_get)

    with pytest.raises(RequestUnavailable):
        fetch_single("Lightning Bolt")

# Scryfall allows 2 requests/second on these endpoints and locks the
# client out for 30s after a 429 - every call must carry those settings,
# not request_with_retries' faster generic defaults.
@pytest.mark.parametrize("call", [
    lambda: fetch_batch(["Lightning Bolt"]),
    lambda: fetch_single("Lightning Bolt"),
])
def test_requests_use_scryfall_pacing(monkeypatch: MonkeyPatch, call: Any) -> None:
    seen: list[dict[str, Any]] = []

    def fake_request_with_retries(method: str, url: str, **kwargs: Any) -> str | None:
        seen.append(kwargs)
        return json.dumps({"name": "Lightning Bolt"})

    monkeypatch.setattr(
        "meta_morphis.scryfall.client.request_with_retries",
        fake_request_with_retries
    )

    call()
    assert seen
    for kwargs in seen:
        assert kwargs["min_delay"] == config.SCRYFALL_MIN_DELAY
        assert kwargs["default_retry_after"] == config.SCRYFALL_RATE_LIMIT_COOLDOWN
        assert kwargs["headers"] == config.SCRYFALL_HEADERS
