import requests
import time
import config

from meta_morphis.db.cards_repo import (
    build_cached_card, 
    get_card_from_cache, 
    save_cards_to_cache
)

def fetch_one_by_one(conn, names):
    cards = []
    print(f"Failed to find {len(names)} card(s) in Scryfall in batch request")
    print(f"This/these card(s) will be fetched from either Scryfall or cache one by one")
    for name in names:
        cached_card = get_card_from_cache(conn, name)
        if cached_card:
            print(f"Card {name} found in cache")
            cards.append(cached_card)
            continue
        
        time.sleep(0.1)
        fetched_card = fetch_single(name)
        if fetched_card:
            print(f"Found card {name} in Scryfall")
            cards.append(fetched_card)
            continue

        print("Not found:", name)
    return cards

def fetch_batch(conn, names):
    all_cards = []
    
    identifiers = [{"name": n} for n in names]

    # Retry loop for robustness
    for attempt in range(3):
        print(f"Fetching cards from Scryfall, attempt {attempt + 1} of 3")
        r = requests.post(config.URL_COLLECTION, json={"identifiers": identifiers}, headers=config.HEADERS, timeout=10)

        if r.status_code == 200:
            all_cards = process_batch_request(conn, r)
            if all_cards:
                return all_cards
        else:
            print(f"Scryfall returned status {r.status_code}")

        time.sleep(0.5 * (attempt + 1))

    print(f"Failed to fetch cards from Scryfall")
    return []

def fetch_batches(conn, batches):
    output = []
    for batch in batches:
        print(f"Fetching {len(batch)} card(s) from Scryfall")
        fetched = fetch_batch(conn, batch)
        if fetched:
            print(f"Saving {len(fetched)} card(s) to cache\n")
            save_cards_to_cache(conn, fetched)
            for raw_card in fetched:
                output.append(build_cached_card(raw_card, 0))
    return output

def fetch_single(name):
    params = {"fuzzy": name}
    for attempt in range(3):
        r = requests.get(config.URL_NAMED, headers=config.HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            raw_card = r.json()
            return raw_card
        time.sleep(0.5 * (attempt + 1))
    print(f"Failed to fetch card {name} from Scryfall after 3 attempts")
    return None

def batch(items, size=config.SCRYFALL_BATCH_SIZE_LIMIT):
    # Scryfall API limits requests to 75 cards per request
    return [items[i:i+size] for i in range(0, len(items), size)]

def classify_cards(conn, meta):
    fresh = []
    outdated = []
    missing = []

    for entry in meta:
        name = entry.name
        cached = get_card_from_cache(conn, name)

        if cached:
            if cached.age > config.SCRYFALL_REFRESH_RATE:
                outdated.append(cached)
            else:
                fresh.append(cached)
        else:
            missing.append(name)

    return fresh, outdated, missing

def refresh_outdated(conn, outdated):
    names = [card["name"] for card in outdated]
    refreshed = fetch_batches(conn, batch(names))
    refreshed_names = {card["name"] for card in refreshed}

    not_refreshed = [card for card in outdated if card["name"] not in refreshed_names]
    return refreshed, not_refreshed

def fetch_cards(conn, meta):
    output = []

    fresh, outdated, missing = classify_cards(conn, meta)
    output.extend(fresh)

    if missing:
        print("Trying to fetch missing names...")
        output.extend(fetch_batches(conn, batch(missing)))

    if outdated:
        print("Trying to fetch outdated names...")
        refreshed, not_refreshed = refresh_outdated(conn, outdated)

        print(f"{len(refreshed)} outdated cards were refreshed successfully")
        output.extend(refreshed)
        
        if not_refreshed:
            print(f"{len(not_refreshed)} outdated cards were not refreshed")
            output.extend(not_refreshed)

    if not output:
        raise RuntimeError("No cards have been fetched either from Scryfall or from cache")
    return output

def process_batch_request(conn, r):
    data = r.json()
    cards = data.get("data", [])
    if not cards:
        print(f"Scryfall error: no data has been received")
        return cards
    not_found = data.get("not_found", [])
    if not_found:
        not_found_names = [item["name"] for item in not_found]
        cards.extend(fetch_one_by_one(conn, not_found_names))

    return cards