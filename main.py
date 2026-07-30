import time
import config

from meta_morphis.db.schema import init_db
from meta_morphis.db.connection import get_connection
from meta_morphis.fetch_from_scryfall import fetch_cards
from meta_morphis.generate_meta import get_meta_cards

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
        cards = fetch_cards(conn, meta)
        for card in cards:         
            print(card)

if __name__ == "__main__":
    main()

# TODO: Refactor the code to make it more readable and maintainable
# TODO: Test fetching cards from Scryfall fallback prevent logic
# TODO: Refactor generate_meta
# TODO: Clean debugging print messages