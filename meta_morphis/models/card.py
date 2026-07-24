from dataclasses import dataclass
from typing import Optional
from meta_morphis.models.card_face import CardFace 


@dataclass
class CachedCard:
    id: str
    name: str
    age: float
    mana_cost: Optional[str]
    type_line: str
    faces: list[CardFace]

    def __str__(self):
        output = (
            f"Name: {self.name}\n"
            f"Type Line: {self.type_line}\n"
            f"Mana Cost: {self.mana_cost}\n"
        )
        for face in self.faces:
            output += f"{face}"

        return output