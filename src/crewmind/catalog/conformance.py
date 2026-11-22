"""The conformance check: every operation is on every surface it belongs on (IF-1.3)."""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import Literal

from crewmind.catalog.registry import Catalog
from crewmind.catalog.surfaces import UNBUILT_SURFACES, Surface, surfaces_for

Problem = Literal["missing", "not expected", "unknown operation"]


@dataclass(frozen=True)
class Violation:
    operation: str
    surface: Surface
    problem: Problem

    def __str__(self) -> str:
        return f"{self.operation} on {self.surface.value}: {self.problem}"


def check_conformance(
    catalog: Catalog,
    built: Mapping[Surface, Set[str]],
    unbuilt: Mapping[Surface, str] = UNBUILT_SURFACES,
) -> list[Violation]:
    """Compare what each built surface exposes with what the catalog says it must (IF-1.3).

    `built` maps each built surface to the operation names it actually exposes. A violation is:
    an operation missing from a surface it belongs on with no written exemption; an operation
    exposed where it does not belong or where it is exempt; or a name no operation defines,
    which is an adapter with no catalog entry behind it (IF-1.2).
    """
    overlap = set(built) & set(unbuilt)
    if overlap:
        names = ", ".join(sorted(surface.value for surface in overlap))
        raise ValueError(f"surfaces both built and listed as not yet built: {names}")
    missing_surfaces = set(Surface) - set(built) - set(unbuilt)
    if missing_surfaces:
        names = ", ".join(sorted(surface.value for surface in missing_surfaces))
        raise ValueError(f"surfaces neither built nor listed as not yet built: {names}")

    violations: list[Violation] = []
    for surface, exposed in built.items():
        expected: set[str] = set()
        for operation in catalog:
            belongs = surface in surfaces_for(operation)
            exempt = surface in operation.exemptions
            if belongs and not exempt:
                expected.add(operation.name)
        for name in sorted(expected - exposed):
            violations.append(Violation(name, surface, "missing"))
        for name in sorted(exposed - expected):
            problem: Problem = "not expected" if name in catalog else "unknown operation"
            violations.append(Violation(name, surface, problem))
    return violations
