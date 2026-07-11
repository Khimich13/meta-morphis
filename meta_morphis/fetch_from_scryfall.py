import requests
import time

from meta_morphis.db.cache import get_card_from_cache, save_card_to_cache, is_card_in_cache

URL_COLLECTION = "https://api.scryfall.com/cards/collection"
URL_NAMED = "https://api.scryfall.com/cards/named"
# Required by Scryfall
HEADERS = {
        "User-Agent": "meta-morphis",
        "Accept": "application/json"
    }

def fetch_one_by_one(conn, names):
    cards = []
    print(f"Failed to find {len(names)} card(s) in Scryfall in batch request")
    print(f"This/these card(s) will be fetched from Scryfall one by one")
    for name in names:
        card = fetch_single(conn, name)
        if card:
            print(f"Found card {name} in Scryfall")
            cards.append(card)
        elif is_card_in_cache(conn, name):
            print(f"Card {name} not found in Scryfall, but in cache")
            cards.append(get_card_from_cache(conn, name))
        else:
            print("Not found:", name)
    return cards

def fetch_batch(conn, names):
    all_cards = []
    
    # Scryfall API limits requests to 75 cards per request
    identifiers = [{"name": n} for n in names[:75]]

    # Retry loop for robustness
    for attempt in range(3):
        print(f"Fetching cards from Scryfall, attempt {attempt + 1} of 3")
        r = requests.post(URL_COLLECTION, json={"identifiers": identifiers}, headers=HEADERS)

        if r.status_code == 200:
            data = r.json()
            if data.get("object") == "error":
                print(f"Scryfall error: {data.get('details')}")
                continue

            if len(data["not_found"]) > 0:
                not_found_names = [item["name"] for item in data.get("not_found", [])]
                all_cards.extend(fetch_one_by_one(conn, not_found_names))

            all_cards.extend(data["data"])
            break

        # Retry on transient errors
        if r.status_code in (429, 503):
            time.sleep(0.5 * (attempt + 1))
            continue
        
        print(f"Failed to fetch cards from Scryfall, attempting to fetch from cache")
        for name in names:
            if not is_card_in_cache(conn, name):
                print(f"Card {name} not found in cache")
                continue
            card = get_card_from_cache(conn, name)
            all_cards.append(card)
                
    if len(all_cards) == 0:
        print(f"Failed to fetch any cards from Scryfall or cache")
        raise(Exception("Failed to fetch any cards from Scryfall or cache"))
    return all_cards

def fetch_single(conn, name):
    params = {"fuzzy": name}
    for attempt in range(3):
        r = requests.get(URL_NAMED, headers=HEADERS, params=params)
        if r.status_code == 200:
            card = r.json()
            save_card_to_cache(conn,card)
            return card
        if r.status_code in (429, 503):
            time.sleep(0.5 * (attempt + 1))
            continue
    print(f"Failed to fetch card {name} from Scryfall after 3 attempts")
    return None

def fetch_cards(conn, meta_list):
    output = []
    missing = []

    for entry in meta_list:
        card_name = entry["name"]
        cached = get_card_from_cache(conn, card_name, refresh_if_stale=True)
        if cached:
            output.append(cached)
        else:
            missing.append(card_name)
    
    # Scryfall API limits requests to 75 cards per request
    for i in range(0, len(missing), 75):
        batch = missing[i:i+75]
        print(f"Fetching {len(batch)} cards from Scryfall")

        for name in batch:
            print(f"Fetching card {name} from Scryfall")
        fetched = fetch_batch(conn, batch)
        for card in fetched:
            save_card_to_cache(conn, card)
        output.extend(fetched)

    return output