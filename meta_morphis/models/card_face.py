from dataclasses import dataclass
from typing import Optional

@dataclass
class CardFace:
    name: str
    mana_cost: Optional[str]
    type_line: str