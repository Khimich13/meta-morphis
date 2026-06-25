import unicodedata

def normalize_name(name: str) -> str:
    # Remove accents, lowercase, strip whitespace
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_only.lower().strip()