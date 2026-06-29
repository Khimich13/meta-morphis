import requests
import time

from meta_morphis.db.cache import get_card_from_cache, save_card_to_cache

URL_COLLECTION = "https://api.scryfall.com/cards/collection"
URL_NAMED = "https://api.scryfall.com/cards/named"

def fetch_cards_from_scryfall(names):
    headers = {
        "User-Agent": "meta-morphis",
        "Accept": "application/json"
    }
    all_cards = []
    
    # Scryfall API limits requests to 75 cards per request
    for i in range(0, len(names), 75):
        batch = names[i:i+75]
        identifiers = [{"name": n} for n in batch]

        # Retry loop for robustness
        for attempt in range(3):
            r = requests.post(URL_COLLECTION, json={"identifiers": identifiers}, headers=headers)

            if r.status_code == 200:
                data = r.json()
                if data.get("object") == "error":
                    raise RuntimeError(f"Scryfall error: {data.get('details')}")

                still_not_found = []
                for item in data["not_found"]:
                    params = {"fuzzy": item["name"]}
                    single_card_r = requests.get(URL_NAMED, headers=headers, params=params)
                    
                    if single_card_r.status_code == 200:
                        all_cards.append(single_card_r.json())
                    else:
                        still_not_found.append(item)
                        
                for item in still_not_found:
                    print("Not found:", item["name"])

                all_cards.extend(data["data"])
                break

            # Retry on transient errors
            if r.status_code in (429, 503):
                time.sleep(0.5 * (attempt + 1))
                continue

            # Hard failure
            r.raise_for_status()
    
    return all_cards
    

def fetch_cards(conn, meta_list):
    output = []
    missing = []
    for entry in meta_list:
        card_name = entry["name"]
        cached = get_card_from_cache(conn, card_name)
        if cached:
            output.append(cached)
        else:
            missing.append(card_name)
    
    if missing:
        fetched = fetch_cards_from_scryfall(missing)
        for card in fetched:
            save_card_to_cache(conn, card)
        output.extend(fetched)

    return output