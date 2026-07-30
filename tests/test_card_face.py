from meta_morphis.models.card_face import CardFace

def test_card_face_empty_mana_cost():
    face = CardFace(name="Test", mana_cost="", type_line="Creature")
    assert face.mana_cost == ""