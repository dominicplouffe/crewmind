"""Secret values in operation inputs and outputs (INV-6, IF-4.5).

Inputs use Pydantic's `SecretStr`, which surfaces read from hidden input and never echo.
An output may carry a secret only once, at the moment it is created: a minted token or a
setup link. Such a field is typed `OneTimeSecret`, and a test lists every one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, get_args

from pydantic import BaseModel


@dataclass(frozen=True)
class ShownOnce:
    """Marks an output field that carries a secret shown once and stored only as a hash."""


OneTimeSecret = Annotated[str, ShownOnce()]


def _shown_once(annotation: Any, metadata: list[Any]) -> bool:
    if any(isinstance(item, ShownOnce) for item in metadata):
        return True
    return any(
        _shown_once(inner, list(getattr(inner, "__metadata__", ())))
        for inner in get_args(annotation)
    )


def one_time_secret_fields(model: type[BaseModel]) -> list[str]:
    """The fields of `model` that carry a one-time secret, optional ones included."""
    return [
        name
        for name, field in model.model_fields.items()
        if _shown_once(field.annotation, field.metadata)
    ]
