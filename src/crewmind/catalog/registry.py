"""The catalog: the registry every surface is generated from (IF-1.1, IF-1.2)."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterator

from crewmind.catalog.operation import CatalogError, Operation


class Catalog:
    """Operations by name. A name is registered once."""

    def __init__(self) -> None:
        self._operations: dict[str, Operation] = {}

    def register(self, operation: Operation) -> Operation:
        if operation.name in self._operations:
            raise CatalogError(f"operation {operation.name} is already registered")
        self._operations[operation.name] = operation
        return operation

    def get(self, name: str) -> Operation:
        try:
            return self._operations[name]
        except KeyError:
            raise CatalogError(f"unknown operation {name}") from None

    def __contains__(self, name: object) -> bool:
        return name in self._operations

    def __iter__(self) -> Iterator[Operation]:
        return iter(sorted(self._operations.values(), key=lambda operation: operation.name))

    def __len__(self) -> int:
        return len(self._operations)


catalog = Catalog()
"""The process-wide catalog. Domain modules register their operations on import."""


def load_domain_modules() -> None:
    """Import every module under `crewmind.domain`, so all operations and rules are registered."""
    import crewmind.domain as domain

    for module in pkgutil.walk_packages(domain.__path__, prefix=f"{domain.__name__}."):
        importlib.import_module(module.name)
