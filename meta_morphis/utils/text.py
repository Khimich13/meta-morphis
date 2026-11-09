import unicodedata


def normalize_name(name: str) -> str:

    name = name.lower().replace("æ", "ae")
    # decompose accents (á → a)
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_only.strip()


def card_count(count: int) -> str:
    """How many cards, e.g. "1 card" or "5 cards"."""
    return f"{count} card" if count == 1 else f"{count} cards"
