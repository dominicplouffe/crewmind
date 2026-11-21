"""The provider registry and model classes, loaded from data (LLM-1, LLM-4)."""

from __future__ import annotations

import re
import tomllib
from enum import StrEnum
from functools import cache
from importlib import resources

from pydantic import BaseModel, ConfigDict


class ModelClass(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    FRONTIER = "frontier"


CLASS_ORDER = [ModelClass.FAST, ModelClass.BALANCED, ModelClass.FRONTIER]


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


class ProviderInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    prefix: str
    needs_base_url: bool
    images: bool
    native_search: bool
    default_harness: str
    classes: tuple[tuple[str, ModelClass], ...]
    default_lineup: dict[ModelClass, str]

    def classify(self, model: str) -> ModelClass | None:
        """The class of a model id, or None when no pattern knows it (LLM-4)."""
        for pattern, model_class in self.classes:
            if re.search(pattern, model, re.IGNORECASE):
                return model_class
        return None


@cache
def providers() -> dict[str, ProviderInfo]:
    text = resources.files(__package__).joinpath("providers.toml").read_text(encoding="utf-8")
    return {
        name: ProviderInfo.model_validate({"name": name, **fields})
        for name, fields in tomllib.loads(text)["providers"].items()
    }


def _version_key(model: str) -> tuple[int, ...]:
    """Orders model ids so that the newest sorts last: by the numbers in the id."""
    return tuple(int(number) for number in re.findall(r"\d+", model))


def pick_lineup(provider: ProviderInfo, models: list[str]) -> dict[ModelClass, str]:
    """The newest reachable model in each class (LLM-4). Unknown models are left out."""
    lineup: dict[ModelClass, str] = {}
    for model in sorted(models, key=_version_key):
        model_class = provider.classify(model)
        if model_class is not None:
            lineup[model_class] = model
    return lineup or dict(provider.default_lineup)


def nearest_class(wanted: ModelClass, available: set[ModelClass]) -> ModelClass | None:
    """The class to run on when `wanted` has no model: the nearest below, else the nearest
    above (LLM-4). The substitution is always shown (P12)."""
    index = CLASS_ORDER.index(wanted)
    for candidate in [*reversed(CLASS_ORDER[: index + 1]), *CLASS_ORDER[index + 1 :]]:
        if candidate in available:
            return candidate
    return None
