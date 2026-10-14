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

# TODO: Clean debugging print messages
# TODO: Add an option to pick the format
# TODO: Update the grid layout when the card's name takes more than one line
# TODO: Is there a way to turn off the scrolling ability while there is nothing to scroll?
# TODO: Think about how to monetize the app in the future
# TODO: Orginize the web files better?