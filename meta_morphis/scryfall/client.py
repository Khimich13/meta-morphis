import json
from typing import Any

from meta_morphis import config
from meta_morphis.utils.http import RequestUnavailable, request_with_retries


def fetch_bulk_info() -> dict[str, Any] | None:
    """Where today's file of every printing is and when it was made:
    jsonl_download_uri, updated_at and compressed_size - see bulk.py"""
    raw = _request("GET", config.SCRYFALL_BULK_DATA_URL)
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


def fetch_catalog(name: str) -> list[str] | None:
    """One of Scryfall's lists of game words, such as "creature-types".
    None if there is no such list."""
    raw = _request("GET", config.SCRYFALL_CATALOG_URL + name)
    if raw is None:
        return None
    words: list[str] = _parse_json(raw).get("data", [])
    return words


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
