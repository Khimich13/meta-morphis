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
            f"Name: {self.name}\n" +
            f"Type Line: {self.type_line}\n"
            f"Mana Cost: "
        )
        if self.faces:
            front_face = self.faces[0]
            back_face = self.faces[1]
            output += f"{front_face.get("mana_cost")}\n"
            output += f"Front Face: {front_face["name"]} ({front_face.get("mana_cost")}) - {front_face["type_line"]}\n"
            output += f"Back Face: {back_face["name"]} ({back_face.get("mana_cost")}) - {back_face["type_line"]}\n"
        else:
            output += f"{self.mana_cost}\n"

        return output