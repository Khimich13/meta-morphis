import requests
import time

from generate_meta import scrape_staple_names

def fetch_many(names):
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
    
    # test
    for card in all_cards:
        print(card["name"], card["mana_cost"], card["type_line"], card["oracle_text"])

fetch_many(scrape_staple_names())

# TODO: save cards 
# TODO: remove tests