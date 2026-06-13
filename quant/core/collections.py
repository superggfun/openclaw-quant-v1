"""Small collection helpers shared across orchestration modules."""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from typing import TypeVar

T = TypeVar("T")


def dedupe_text(values: Iterable[object]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def dedupe_by(values: Iterable[T], key: str | tuple[str, ...]) -> list[T]:
    keys = (key,) if isinstance(key, str) else key
    output: list[T] = []
    seen: set[Hashable] = set()
    for value in values:
        if not isinstance(value, dict):
            identity: Hashable = value  # type: ignore[assignment]
        elif len(keys) == 1:
            identity = value[keys[0]]
        else:
            identity = tuple(value[item] for item in keys)
        if identity not in seen:
            output.append(value)
            seen.add(identity)
    return output
