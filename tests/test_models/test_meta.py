from meta_morphis.models.meta import MetaEntry

def test_meta_entry_creation():
    meta_item = MetaEntry("Test", 1, 0.5, 10)
    assert meta_item.name == "Test"
    assert meta_item.rank == 1
    assert meta_item.percent == 0.5
    assert meta_item.deck_count == 10