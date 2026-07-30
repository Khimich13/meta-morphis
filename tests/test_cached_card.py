from meta_morphis.models.card import CachedCard
from meta_morphis.models.card_face import CardFace

def test_cached_card_creation():
    face = CardFace("Test", None, "Creature")
    card = CachedCard("123", "Test Card", 0, None, "Creature", [face])
    assert card.id == "123"
    assert card.faces[0].name == "Test"
