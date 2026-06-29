import sqlite3
import time

from meta_morphis.db.schema import init_db
from meta_morphis.fetch_cards import fetch_cards
from meta_morphis.generate_meta import get_meta_cards
from meta_morphis.formats import FORMATS

CONN = sqlite3.connect("cards.db")

def choose_format() -> str:
    while True:
        print("Print the name of the format:\n")
        for format, _ in FORMATS.items():
            print(f"{format}")
        print()

        response = input().strip().lower()

        if response in FORMATS:
            return response

        print("Invalid choice!")
        print("Please, choose between the provided options\n")
        time.sleep(2)


def main():
    init_db(CONN)

    format = choose_format()
    print(f"You chose: {format}\n")

    meta = get_meta_cards(CONN, format)
    cards = fetch_cards(CONN, meta)
    for card in cards:
        name = card["name"]
        type_line = card["type_line"]
        mana_value = ""

        if "mana_cost" in card:
            mana_value = card["mana_cost"]
        # covers double-faced and other differently structured cards
        elif "card_faces" in card:
            mana_value = card["card_faces"][0]["mana_cost"]
            
        print(name, mana_value, type_line)

    CONN.close()

if __name__ == "__main__":
    main()

# TODO: fetch from cache if internet/scryfall/goldfish are down
# TODO: deal with the pioneer format's bug: Not found: [{'name': 'Unholy Annex // Ritual Chamber\n\n //'}]