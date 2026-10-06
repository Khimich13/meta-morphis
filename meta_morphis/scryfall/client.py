import json
from typing import Any

from meta_morphis import config
from meta_morphis.utils.http import RequestUnavailable, request_with_retries


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
    return _parse_json(raw)

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
    return _parse_json(raw)

def _parse_json(raw: str) -> dict[str, Any]:
    # A 200 whose body isn't JSON (a proxy or antivirus block page, say)
    # is not Scryfall saying "no such card" - returning None here would
    # get a real name recorded in card_lookup_failures.
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RequestUnavailable(f"response was not valid JSON: {e}") from e
    return data
