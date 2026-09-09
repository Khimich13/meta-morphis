from dataclasses import dataclass
from typing import Optional


@dataclass
class MetaEntry:
    name: str
    rank: int
    percent: float
    avg_copies: float
    lookup_name: Optional[str] = None