import json
from typing import Any

from meta_morphis import config
from meta_morphis.utils.http import RequestUnavailable, request_with_retries


def fetch_batch(names: list[str]) -> dict[str, Any] | None:
    identifiers = [{"name": n} for n in names]

    raw = _request(
        "POST",
        config.SCRYFALL_COLLECTION_URL,
        json={"identifiers": identifiers},
    )
    if raw is None:
        return None
    return _parse_json(raw)

def fetch_single(name: str) -> dict[str, Any] | None:
    raw = _request("GET", config.SCRYFALL_NAMED_URL, params={"exact": name})
    if raw is None:
        raw = _request("GET", config.SCRYFALL_NAMED_URL, params={"fuzzy": name})
    if raw is None:
        return None
    return _parse_json(raw)

def fetch_symbology() -> dict[str, Any] | None:
    # Every card symbol ({U}, {T}, hybrid, Phyrexian...) with its SVG
    # and an English description, in one list response.
    raw = _request("GET", config.SCRYFALL_SYMBOLOGY_URL)
    if raw is None:
        return None
    return _parse_json(raw)

def search_printings(oracle_id: str) -> list[dict[str, Any]] | None:
    """Every regular printing of a card, oldest first. None means Scryfall
    found no printing matching the filters.
    """
    params = {
        "q": f"oracleid:{oracle_id} {config.SCRYFALL_REGULAR_PRINTINGS}",
        "unique": "prints",
        "order": "released",
        "dir": "asc",
    }
    raw = _request("GET", config.SCRYFALL_SEARCH_URL, params=params)
    if raw is None:
        return None
    page = _parse_json(raw)
    printings: list[dict[str, Any]] = list(page.get("data", []))

    # Results come in pages of 175 - only cards with a very long print
    # history need more than one
    while page.get("has_more") and page.get("next_page"):
        raw = _request("GET", page["next_page"])
        if raw is None:
            raise RequestUnavailable("a further page of search results was missing")
        page = _parse_json(raw)
        printings.extend(page.get("data", []))
    return printings

def _request(
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> str | None:
    # Every Scryfall call goes through here so none of them can skip the
    # API's pacing and 429-lockout rules.
    return request_with_retries(
        method,
        url=url,
        headers=config.SCRYFALL_HEADERS,
        params=params,
        json=json,
        min_delay=config.SCRYFALL_MIN_DELAY,
        default_retry_after=config.SCRYFALL_RATE_LIMIT_COOLDOWN,
    )

def _parse_json(raw: str) -> dict[str, Any]:
    # A 200 whose body isn't JSON (a proxy or antivirus block page, say)
    # is not Scryfall saying "no such card" - returning None here would
    # get a real name recorded in card_lookup_failures.
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RequestUnavailable(f"response was not valid JSON: {e}") from e
    return data
