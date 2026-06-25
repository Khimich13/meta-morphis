import sqlite3

from meta_morphis.db.schema import init_db
from meta_morphis.fetch_cards import fetch_cards
from meta_morphis.generate_meta import get_meta_cards

CONN = sqlite3.connect("cards.db")

init_db(CONN)

meta = get_meta_cards(CONN)
cards = fetch_cards(CONN, meta)

for card in cards:
    print(card["name"], card["mana_cost"], card["type_line"], card["oracle_text"])

CONN.close()

# TODO: add different formats
# TODO: fetch from cache if internet/scryfall/goldfish are down
# TODO: fix a major bug, user's format choice is getting ignored and program no matter what sends them cached data