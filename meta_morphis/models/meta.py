from dataclasses import dataclass
from typing import Optional

@dataclass
class MetaEntry:
    name: str
    rank: int
    percent: float
    deck_count: float
    lookup_name: Optional[str] = None