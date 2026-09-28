from typing import TypeVar

T = TypeVar("T")


def chunked(items: list[T], size: int) -> list[list[T]]:
    """Split `items` into consecutive chunks of at most `size` elements."""
    if size < 1:
        raise ValueError(f"chunk size must be at least 1, got {size}")
    return [items[i:i + size] for i in range(0, len(items), size)]
