from meta_morphis.scryfall.client import (
    fetch_batch,
    fetch_single,
    batch
)

import config

class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload

def test_fetch_batch_success(monkeypatch):
    def fake_post(url, json, headers, timeout):
        assert url == config.URL_COLLECTION
        assert json == {"identifiers": [{"name": "Lightning Bolt"}]}
        return FakeResponse(200, {"data": "ok"})

    monkeypatch.setattr("requests.post", fake_post)

    result = fetch_batch(["Lightning Bolt"])
    assert result == {"data": "ok"}

def test_fetch_batch_failure(monkeypatch):
    def fake_post(url, json, headers, timeout):
        return FakeResponse(500, None)

    monkeypatch.setattr("requests.post", fake_post)

    monkeypatch.setattr("time.sleep", lambda x: None)


    result = fetch_batch(["Bolt"])
    assert result is None

def test_fetch_single_success(monkeypatch):
    def fake_get(url, headers, params, timeout):
        assert params == {"fuzzy": "Lightning Bolt"}
        return FakeResponse(200, {"name": "Lightning Bolt"})

    monkeypatch.setattr("requests.get", fake_get)

    result = fetch_single("Lightning Bolt")
    assert result == {"name": "Lightning Bolt"}

def test_fetch_single_failure(monkeypatch):
    def fake_get(url, headers, params, timeout):
        return FakeResponse(404, None)

    monkeypatch.setattr("requests.get", fake_get)

    monkeypatch.setattr("time.sleep", lambda x: None)

    result = fetch_single("Unknown Card")
    assert result is None

def test_batch():
    names = ["a", "b", "c", "d", "e"]
    result = batch(names, size=2)
    assert result == [["a", "b"], ["c", "d"], ["e"]]