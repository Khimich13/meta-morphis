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

def fetch_cards_from_scryfall(conn,names):
    all_cards = []
    
    # Scryfall API limits requests to 75 cards per request
    for i in range(0, len(names), 75):
        batch = names[i:i+75]
        identifiers = [{"name": n} for n in batch]

        # Retry loop for robustness
        for attempt in range(3):
            print(f"Fetching cards from Scryfall, attempt {attempt + 1} of 3")
            r = requests.post(URL_COLLECTION, json={"identifiers": identifiers}, headers=HEADERS)

            if r.status_code == 200:
                data = r.json()
                if data.get("object") == "error":
                    print(f"Scryfall error: {data.get('details')}")
                    continue

                still_not_found = []
                if len(data["not_found"]) > 0:
                    print(f"Failed to find {len(data['not_found'])} card(s) in Scryfall in batch request")
                    print(f"These card(s) will be fetched from Scryfall one by one")
                for item in data["not_found"]:
                    card = fetch_single_card_from_scryfall(conn,item["name"])
                    if card:
                        print(f"Found card {item['name']} in Scryfall")
                        all_cards.append(card)
                    elif is_card_in_cache(conn, item["name"]):
                        print(f"Card {item['name']} not found in Scryfall, but in cache")
                        all_cards.append(get_card_from_cache(conn, item["name"]))
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
            
            print(f"Failed to fetch cards from Scryfall, attempting to fetch from cache")
            for name in batch:
                if not is_card_in_cache(conn, name):
                    print(f"Card {name} not found in cache")
                    continue
                card = get_card_from_cache(conn, name)
                all_cards.append(card)
                
    if len(all_cards) == 0:
        print(f"Failed to fetch any cards from Scryfall or cache")
        raise(Exception("Failed to fetch any cards from Scryfall or cache"))
    return all_cards

def fetch_single_card_from_scryfall(conn, name):
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
    
    if missing:
        print(f"Fetching {len(missing)} cards from Scryfall")
        fetched = fetch_cards_from_scryfall(conn, missing)
        for card in fetched:
            save_card_to_cache(conn, card)
        output.extend(fetched)

    return output