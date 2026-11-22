"""The requirement graph: dependencies stay acyclic, and the longest chain is known
(PLN-2, INV-19, SPD-2). Pure functions over a mapping of requirement to what it needs."""

from __future__ import annotations

Graph = dict[int, set[int]]
"""Each requirement id and the ids it depends on."""


def loop_if_added(graph: Graph, requirement: int, depends_on: int) -> list[int] | None:
    """The loop that adding `requirement -> depends_on` would close, as the ids in order, or
    None when the graph stays acyclic (INV-19)."""
    if requirement == depends_on:
        return [requirement, requirement]
    path: list[int] = [depends_on]
    seen: set[int] = set()

    def reach(node: int) -> bool:
        if node == requirement:
            return True
        if node in seen:
            return False
        seen.add(node)
        for needed in sorted(graph.get(node, set())):
            path.append(needed)
            if reach(needed):
                return True
            path.pop()
        return False

    return [requirement, *path] if reach(depends_on) else None


def longest_chain(graph: Graph, lengths: dict[int, int]) -> tuple[int, list[int]]:
    """The dependency chain that takes the most runs, and its total (SPD-2). `lengths` gives
    each requirement's runs; a requirement with none counts as nothing."""
    best: dict[int, tuple[int, list[int]]] = {}

    def chain(node: int, walking: frozenset[int]) -> tuple[int, list[int]]:
        if node in best:
            return best[node]
        longest: tuple[int, list[int]] = (0, [])
        for needed in sorted(graph.get(node, set())):
            if needed in walking or needed not in lengths:
                continue
            candidate = chain(needed, walking | {node})
            if candidate[0] > longest[0]:
                longest = candidate
        best[node] = (longest[0] + lengths.get(node, 0), [*longest[1], node])
        return best[node]

    result: tuple[int, list[int]] = (0, [])
    for node in sorted(lengths):
        candidate = chain(node, frozenset())
        if candidate[0] > result[0]:
            result = candidate
    return result
