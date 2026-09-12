import json
from typing import Any

import config
from meta_morphis.utils.http import request_with_retries


def fetch_batch(names: list[str]) -> dict[str, Any] | None:
    identifiers = [{"name": n} for n in names]

    raw = request_with_retries(
        "POST",
        config.URL_COLLECTION,
        headers=config.HEADERS,
        json={"identifiers": identifiers},
    )
    if raw is None:
        return None
    data: dict[str, Any] = json.loads(raw)
    return data

def fetch_single(name: str) -> dict[str, Any] | None:
    raw = request_with_retries(
        "GET",
        url=config.URL_NAMED,
        headers=config.HEADERS,
        params={"fuzzy": name}
    )
    if raw is None:
        return None
    data: dict[str, Any] = json.loads(raw)
    return data

def batch(names: list[str], size: int=config.SCRYFALL_BATCH_SIZE_LIMIT) -> list[list[str]]:
    return [names[i:i+size] for i in range(0, len(names), size)]