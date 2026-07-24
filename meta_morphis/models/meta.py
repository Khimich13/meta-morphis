from dataclasses import dataclass

@dataclass
class MetaEntry:
    name: str
    rank: int
    percent: float
    deck_count: float