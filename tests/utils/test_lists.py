import pytest

from meta_morphis.utils.lists import chunked


def test_chunked() -> None:
    assert chunked(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]]

def test_chunked_empty() -> None:
    assert chunked([], 3) == []

def test_chunked_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError):
        chunked(["a"], 0)
    with pytest.raises(ValueError):
        chunked(["a"], -1)
