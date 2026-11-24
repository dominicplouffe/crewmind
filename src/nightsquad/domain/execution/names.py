"""The first names agents are given when nobody names them (EXE-18).

A seat's `name` is its identity (events, mentions, scripts); its display name is what people
read. A seat hired with names takes the name it was given. Every other seat (the CEO, a
reviewer the platform staffs, a team hired by count) gets a first name from `POOL`: the
first one not yet used in the project, walking the pool from a start point that a hash of
the project id decides, so the same project always draws the same names.

The pool is data: short, easy to read, from many cultures, no famous people and no titles.
It leaves out the names the shipped squads and the demo already give their members, so a
squad's own names never collide with a drawn one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

POOL: tuple[str, ...] = (
    "Lena", "Omar", "Hana", "Mateo", "Zara", "Kenji", "Aiko", "Ravi", "Lucia", "Tariq",
    "Elena", "Jonas", "Amara", "Diego", "Yara", "Felix", "Leila", "Arjun", "Mei", "Hugo",
    "Selin", "Kofi", "Ingrid", "Rosa", "Emil", "Alma", "Bilal", "Clara", "Darius", "Esme",
    "Farah", "Ilse", "Jada", "Lars", "Malik", "Nora", "Oskar", "Paloma", "Rania", "Sami",
    "Talia", "Vera", "Xavi", "Yusuf", "Zoe", "Anya", "Bruno", "Dara", "Freya", "Hiro",
    "Jin", "Kira", "Luca", "Mira", "Nico", "Pia", "Suki", "Tess", "Uma", "Wei",
)  # fmt: skip

DISPLAY_NAME_MAX = 100


def tidy(name: str) -> str:
    """One space between words, none at either end."""
    return " ".join(name.split())


def _order(project_id: str) -> list[str]:
    start = int(hashlib.sha256(project_id.encode("utf-8")).hexdigest(), 16) % len(POOL)
    return [*POOL[start:], *POOL[:start]]


def draw(project_id: str, taken: Iterable[str]) -> str:
    """The first pool name not in `taken` (compared without case), in this project's order.
    When every one is used, the pool goes round again as "<name> 2", "<name> 3" and so on."""
    used = {name.casefold() for name in taken}
    order = _order(project_id)
    round_number = 1
    while True:
        for name in order:
            candidate = name if round_number == 1 else f"{name} {round_number}"
            if candidate.casefold() not in used:
                return candidate
        round_number += 1
