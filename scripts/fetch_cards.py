import requests
import time

from generate_meta import scrape_staple_names
from db.schema import init_db
from db.cache import get_card_from_cache, save_card_to_cache


def fetch_cards_from_scryfall(names):
    url = "https://api.scryfall.com/cards/collection"
    headers = {
        "User-Agent": "meta-morphis",
        "Accept": "application/json"
    }
    all_cards = []
    
    # Scryfall API limits requests to 75 cards per request
    for i in range(0, len(names), 75):
        batch = names[i:i+75]
        identifiers = [{"name": n, "unique": "exact"} for n in batch]

        # Retry loop for robustness
        for attempt in range(3):
            r = requests.post(url, json={"identifiers": identifiers}, headers=headers)

            if r.status_code == 200:
                data = r.json()
                if data.get("object") == "error":
                    raise RuntimeError(f"Scryfall error: {data.get('details')}")
                all_cards.extend(data["data"])
                break

            # Retry on transient errors
            if r.status_code in (429, 503):
                time.sleep(0.5 * (attempt + 1))
                continue

            # Hard failure
            r.raise_for_status()
    
    return all_cards
    

def fetch_cards(names):
    init_db()
    output = []
    missing = []
    for name in names:
        cashed = get_card_from_cache(name)
        if cashed:
            print("from cache", name)
            output.append(get_card_from_cache(name))
        else:
            print("not from cache", name)
            missing.append(name)
    
    if missing:
        fetched = fetch_cards_from_scryfall(missing)
        for card in fetched:
            save_card_to_cache(card)
        output.extend(fetched)

    # test
    for card in output:
        print(card["name"], card["mana_cost"], card["type_line"], card["oracle_text"])
    return output

# test
fetch_cards(scrape_staple_names())

# TODO: cache logic for goldfish website
# TODO: remove tests