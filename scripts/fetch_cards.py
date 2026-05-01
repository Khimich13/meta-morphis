import requests
from generate_meta import scrape_staple_names

def fetch_many(names):
    url = "https://api.scryfall.com/cards/collection"
    identifiers = [{"name": n} for n in names]

    r = requests.post(url, json={"identifiers": identifiers})
    r.raise_for_status()
    cards = r.json()["data"]
    
    for card in cards:
        print(card["name"], card["mana_cost"], card["type_line"], card["oracle_text"])

fetch_many(scrape_staple_names())

# TODO: handle 75 cards limit per request
# TODO: remove all print method