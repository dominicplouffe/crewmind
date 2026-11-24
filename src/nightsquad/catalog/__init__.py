"""The operation catalog: every domain action defined once (P11, IF-1.1 to IF-1.4)."""

from nightsquad.catalog.conformance import Violation, check_conformance
from nightsquad.catalog.operation import (
    CatalogError,
    Operation,
    Principal,
    Reversibility,
)
from nightsquad.catalog.refusal import ErrorEnvelope, Refusal, RefusalKind
from nightsquad.catalog.registry import Catalog, catalog
from nightsquad.catalog.rules import Rule, RuleMode, RuleRegistry, rules
from nightsquad.catalog.surfaces import UNBUILT_SURFACES, Surface, surfaces_for

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
