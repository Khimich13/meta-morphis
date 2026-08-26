from dataclasses import dataclass
from typing import Any

from meta_morphis.models.card_face import CardFace


@dataclass
class Card:
    id: str
    name: str
    mana_cost: str | None
    type_line: str
    faces: list[CardFace]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Card":
        faces = []

        # Build CardFace objects if present
        if "card_faces" in raw:
            for face in raw["card_faces"]:
                faces.append(CardFace(
                    name=face["name"],
                    mana_cost=face.get("mana_cost") or None,
                    type_line=face["type_line"]
                ))

        # Determine mana_cost
        if faces:
            mana_cost = faces[0].mana_cost
        else:
            mana_cost = raw.get("mana_cost")

        return Card(
            id=raw["id"],
            name=raw["name"],
            mana_cost=mana_cost,
            type_line=raw.get("type_line", ""),
            faces=faces
        )

    def __str__(self) -> str:
        output = (
            f"Name: {self.name}\n"
            f"Type Line: {self.type_line}\n"
            f"Mana Cost: {self.mana_cost}\n"
        )
        for face in self.faces:
            output += f"{face}"

        return output