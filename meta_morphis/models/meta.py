from dataclasses import dataclass


@dataclass
class MetaEntry:
    name: str
    rank: int | None = None
    percent: float | None = None
    avg_copies: float | None = None
    lookup_name: str | None = None