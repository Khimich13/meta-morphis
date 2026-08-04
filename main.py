import time
import config

from meta_morphis.db.init_db import init_db
from meta_morphis.db.connection import get_connection
from meta_morphis.scryfall.client import fetch_cards
from meta_morphis.meta.service import get_meta_cards
from meta_morphis.models.card import Card

def choose_format() -> str:
    while True:
        print("Print the name of the format:\n")
        for format, _ in config.FORMATS.items():
            print(f"{format}")
        print()

        response = input().strip().lower()

        if response in config.FORMATS:
            return response

        print("Invalid choice!")
        print("Please, choose between the provided options\n")
        time.sleep(2)

def main():
    with get_connection() as conn:
        init_db(conn)

        format = choose_format()
        print(f"You chose: {format}\n")

        meta = get_meta_cards(conn, format)
        raw_cards = fetch_cards(conn, meta)
        for raw in raw_cards:
            print(Card.from_raw(raw))

if __name__ == "__main__":
    main()

# TODO: Test fetching cards from Scryfall fallback prevent logic
# TODO: Clean debugging print messages
# TODO: Should I create CLI???