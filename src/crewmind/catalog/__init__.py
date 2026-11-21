"""The operation catalog: every domain action defined once (P11, IF-1.1 to IF-1.4)."""

from crewmind.catalog.conformance import Violation, check_conformance
from crewmind.catalog.operation import (
    CatalogError,
    Operation,
    Principal,
    Reversibility,
)
from crewmind.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from crewmind.catalog.registry import Catalog, catalog
from crewmind.catalog.rules import Rule, RuleMode, RuleRegistry, rules
from crewmind.catalog.surfaces import UNBUILT_SURFACES, Surface, surfaces_for

__all__ = [
    "UNBUILT_SURFACES",
    "Catalog",
    "CatalogError",
    "ErrorEnvelope",
    "Operation",
    "Principal",
    "Refusal",
    "RefusalKind",
    "Reversibility",
    "Rule",
    "RuleMode",
    "RuleRegistry",
    "Surface",
    "Violation",
    "catalog",
    "check_conformance",
    "rules",
    "surfaces_for",
]
