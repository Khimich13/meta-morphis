from dataclasses import dataclass
from meta_morphis.models.card_face import CardFace 
from typing_extensions import Any


@dataclass
class CachedCard:
    id: str
    name: str
    age: float
    mana_cost: str | None
    type_line: str
    faces: list[CardFace]
    raw: dict[str, Any]

    def __str__(self) -> str:
        output = (
            f"Name: {self.name}\n"
            f"Type Line: {self.type_line}\n"
            f"Mana Cost: {self.mana_cost}\n"
        )
        for face in self.faces:
            output += f"{face}"

        return output