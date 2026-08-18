import requests
import time
import config

from typing_extensions import Any

def fetch_batch(names: list[str]) -> dict[str, Any] | None:
    identifiers = [{"name": n} for n in names]
    # Retry loop for robustness
    for attempt in range(3):
        print(f"Fetching cards from Scryfall, attempt {attempt + 1} of 3")
        r = requests.post(config.URL_COLLECTION, json={"identifiers": identifiers}, headers=config.HEADERS, timeout=10)
        if r.status_code == 200:
            raw: dict[str, Any] = r.json()
            return raw
        print(f"Scryfall returned status {r.status_code}")
        time.sleep(0.5 * (attempt + 1))

    print(f"Failed to fetch cards from Scryfall")
    return None

def fetch_single(name: str) -> dict[str, Any] | None:
    params = {"fuzzy": name}
    for attempt in range(3):
        r = requests.get(config.URL_NAMED, headers=config.HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            raw_card: dict[str, Any] = r.json()
            return raw_card
        time.sleep(0.5 * (attempt + 1))
    print(f"Failed to fetch card {name} from Scryfall after 3 attempts")
    return None

def batch(names: list[str], size: int=config.SCRYFALL_BATCH_SIZE_LIMIT) -> list[list[str]]:
    return [names[i:i+size] for i in range(0, len(names), size)]