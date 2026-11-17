import json
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.scryfall.client import (
    fetch_bulk_info,
    fetch_catalog,
    fetch_symbology,
)
from meta_morphis.utils.http import RequestUnavailable


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


def test_fetch_bulk_info_success(monkeypatch: MonkeyPatch) -> None:
    info = {
        "type": "default_cards",
        "updated_at": "2026-11-17T22:06:47.962+00:00",
        "jsonl_download_uri": "https://data.scryfall.io/default-cards/x.jsonl.gz",
        "compressed_size": 81227194,
    }

    def fake_get(method: str, url: str, **kwargs: Any) -> FakeResponse:
        assert method == "GET"
        assert url == config.SCRYFALL_BULK_DATA_URL
        return FakeResponse(200, info)

    monkeypatch.setattr("requests.request", fake_get)

    assert fetch_bulk_info() == info


def test_fetch_bulk_info_failure(monkeypatch: MonkeyPatch) -> None:
    # A 500 exhausting all retries means "couldn't complete the request" -
    # it propagates, so the caller keeps its last copy of the file
    monkeypatch.setattr("requests.request", lambda *a, **k: FakeResponse(500, {}))
    monkeypatch.setattr("time.sleep", lambda x: None)

    with pytest.raises(RequestUnavailable):
        fetch_bulk_info()


def test_fetch_bulk_info_bad_200_response(monkeypatch: MonkeyPatch) -> None:
    # A 200 status doesn't guarantee a JSON body - e.g. a Cloudflare
    # interstitial or a truncated proxy response
    def fake_get(method: str, url: str, **kwargs: Any) -> FakeResponse:
        response = FakeResponse(200, {})
        response.text = "<html>Just a moment...</html>"
        return response

    monkeypatch.setattr("requests.request", fake_get)

    with pytest.raises(RequestUnavailable):
        fetch_bulk_info()


# Scryfall allows 2 requests/second on its API and locks the
# client out for 30s after a 429 - every call must carry those settings,
# not request_with_retries' faster generic defaults.
@pytest.mark.parametrize(
    "call",
    [
        lambda: fetch_bulk_info(),
        lambda: fetch_symbology(),
        lambda: fetch_catalog("creature-types"),
    ],
)
def test_requests_use_scryfall_pacing(monkeypatch: MonkeyPatch, call: Any) -> None:
    seen: list[dict[str, Any]] = []

    def fake_request_with_retries(method: str, url: str, **kwargs: Any) -> str | None:
        seen.append(kwargs)
        return json.dumps({"name": "Lightning Bolt"})

    monkeypatch.setattr(
        "meta_morphis.scryfall.client.request_with_retries", fake_request_with_retries
    )

    call()
    assert seen
    for kwargs in seen:
        assert kwargs["min_delay"] == config.SCRYFALL_MIN_DELAY
        assert kwargs["default_retry_after"] == config.SCRYFALL_RATE_LIMIT_COOLDOWN
        assert kwargs["headers"] == config.SCRYFALL_HEADERS


def test_fetch_symbology_success(monkeypatch: MonkeyPatch) -> None:
    payload = {
        "object": "list",
        "data": [
            {
                "symbol": "{U}",
                "english": "one blue mana",
                "svg_uri": "https://svgs.scryfall.io/card-symbols/U.svg",
            }
        ],
    }

    def fake_get(method: str, url: str, **kwargs: Any) -> FakeResponse:
        assert method == "GET"
        assert url == config.SCRYFALL_SYMBOLOGY_URL
        return FakeResponse(200, payload)

    monkeypatch.setattr("requests.request", fake_get)

    assert fetch_symbology() == payload


def test_fetch_symbology_bad_200_response(monkeypatch: MonkeyPatch) -> None:
    # A block page served as 200 is "we don't know", not an empty list
    class HtmlResponse(FakeResponse):
        def __init__(self) -> None:
            super().__init__(200, {})
            self.text = "<html>blocked</html>"

    monkeypatch.setattr("requests.request", lambda *a, **k: HtmlResponse())

    with pytest.raises(RequestUnavailable):
        fetch_symbology()
