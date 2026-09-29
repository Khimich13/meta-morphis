import json
from typing import Any

from meta_morphis import config
from meta_morphis.utils.http import request_with_retries


def fetch_batch(names: list[str]) -> dict[str, Any] | None:
    identifiers = [{"name": n} for n in names]

    raw = request_with_retries(
        "POST",
        config.SCRYFALL_COLLECTION_URL,
        headers=config.SCRYFALL_HEADERS,
        json={"identifiers": identifiers},
    )
    if raw is None:
        return None
    try:
        data: dict[str, Any] = json.loads(raw)
        return data
    except json.JSONDecodeError:
        return None

def fetch_single(name: str) -> dict[str, Any] | None:
    raw = request_with_retries(
        "GET",
        url=config.SCRYFALL_NAMED_URL,
        headers=config.SCRYFALL_HEADERS,
        params={"exact": name}
    )
    if raw is None:
        raw = request_with_retries(
            "GET",
            url=config.SCRYFALL_NAMED_URL,
            headers=config.SCRYFALL_HEADERS,
            params={"fuzzy": name}
        )
    if raw is None:
        return None
    try:
        data: dict[str, Any] = json.loads(raw)
        return data
    except json.JSONDecodeError:
        return None
