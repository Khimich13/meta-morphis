import logging
import time

from meta_morphis import config
from meta_morphis.db.connection import get_connection
from meta_morphis.db.init_db import init_db
from meta_morphis.meta.service import get_meta_cards
from meta_morphis.scryfall.service import fetch_cards


def choose_format() -> str:
    while True:
        print("Print the name of the format:\n")
        for format_name, _ in config.GOLDFISH_FORMAT_URLS.items():
            print(f"{format_name}")
        print()

        response = input().strip().lower()

        if response in config.GOLDFISH_FORMAT_URLS:
            return response

        print("Invalid choice!")
        print("Please, choose between the provided options\n")
        time.sleep(2)

def main() -> None:
    # Show the library's progress and warnings as plain lines
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with get_connection() as conn:
        init_db(conn)

        format_name = choose_format()
        print(f"You chose: {format_name}\n")

        meta = get_meta_cards(conn, format_name)
        cards = fetch_cards(conn, meta)
        for card in cards:
            print(card)

if __name__ == "__main__":
    main()

# TODO: Add an option to pick the format
# TODO: Think about how to monetize the app in the future
# TODO: Add commander
# TODO: Change the background to deal with the color of the cards
# TODO: Add sound effects?
# TODO: Add voice naming the cards?
# TODO: Make a better game icon
# TODO: Improve design
# TODO: What to do with this file (main.py)?
# TODO: Show user what cards entered the meta and which left
# TODO: Inform user of bans / unbans
# TODO: Ask Claude about the current database structure. Does it make sense to have a db in the backend now?