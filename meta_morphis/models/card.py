from dataclasses import dataclass
from typing import Optional
from meta_morphis.models.card_face import CardFace 

@dataclass
class CachedCard:
    id: str
    name: str
    mana_cost: Optional[str]
    type_line: str
    faces: list[CardFace]