from dataclasses import dataclass
from typing import Optional

@dataclass
class CardFace:
    name: str
    mana_cost: Optional[str]
    type_line: str

    def __str__(self):
        return (
            f"Face Name: {self.name}\n"
            f"Type Line: {self.type_line}\n"
            f"Mana Cost: {self.mana_cost}\n"
        )