"""The settings registry: every governed setting, constraint and operational variable.

The data is `registry.toml`, transcribed from Appendix A of the spec. No tunable number
lives in code: code reads values through the settings service, which reads definitions here.
Changing a setting's value (GOV-1) is the settings service's job, not this module's.
"""

from __future__ import annotations

import difflib
import re
import tomllib
from enum import StrEnum
from functools import cache
from importlib import resources
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict

SettingValue = int | float | bool | str

_TIME_OF_DAY = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class SettingType(StrEnum):
    ENUM = "enum"
    BOOL = "bool"
    INT = "int"
    PERCENT = "percent"
    DURATION = "duration"
    TOKENS = "tokens"
    BYTES = "bytes"
    MONEY = "money"
    TIME_OF_DAY = "time_of_day"
    CURRENCY = "currency"
    URL = "url"
    TIMEZONE = "timezone"
    STRING = "string"
    PATH = "path"


_WHOLE_NUMBERS = {
    SettingType.INT,
    SettingType.PERCENT,
    SettingType.DURATION,
    SettingType.TOKENS,
    SettingType.BYTES,
}


class Scope(StrEnum):
    """Who changes a setting, and how (GOV-1)."""

    PROJECT = "project"
    PERSON = "person"
    INSTALL = "install"


class SettingValueError(ValueError):
    """A value is outside its setting's type or range."""


class UnknownSettingError(KeyError):
    """No setting has this name. `closest` is the nearest real name, if any (GOV-1)."""

    def __init__(self, name: str, closest: str | None) -> None:
        super().__init__(name)
        self.name = name
        self.closest = closest

    def __str__(self) -> str:
        if self.closest is None:
            return f"There is no setting named {self.name}."
        return f"There is no setting named {self.name}. Did you mean {self.closest}?"


class DefaultBy(BaseModel):
    """A default that depends on another value, such as the project type."""

    model_config = ConfigDict(frozen=True)

    setting: str
    values: dict[str, SettingValue]


class Definition(BaseModel):
    """The type, default and range shared by governed and operational settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    type: SettingType
    default: SettingValue | None = None
    default_from: str | None = None
    default_by: DefaultBy | None = None
    min: float | None = None
    max: float | None = None
    zero_means_off: bool = False
    choices: tuple[str, ...] = ()
    specials: tuple[str, ...] = ()
    used_by: tuple[str, ...]
    spec_default: str
    spec_range: str

    def validate_value(self, value: object) -> SettingValue:
        """Return `value` if it is allowed for this setting; raise `SettingValueError` if not."""
        if isinstance(value, str) and value in self.specials:
            return value
        match self.type:
            case SettingType.BOOL:
                if isinstance(value, bool):
                    return value
                raise self._refuse(value, "on or off")
            case SettingType.ENUM:
                if isinstance(value, str) and value in self.choices:
                    return value
                raise self._refuse(value, f"one of {', '.join(self.choices)}")
            case SettingType.MONEY:
                if isinstance(value, int | float) and not isinstance(value, bool):
                    return self._in_range(value)
                raise self._refuse(value, "a number")
            case SettingType.TIME_OF_DAY:
                if isinstance(value, str) and _TIME_OF_DAY.match(value):
                    return value
                raise self._refuse(value, "a time as HH:MM")
            case SettingType.CURRENCY:
                if isinstance(value, str) and _CURRENCY.match(value):
                    return value
                raise self._refuse(value, "an ISO 4217 currency code")
            case SettingType.URL:
                if isinstance(value, str) and _is_url(value):
                    return value
                raise self._refuse(value, "an http or https URL")
            case SettingType.TIMEZONE:
                if isinstance(value, str) and _is_timezone(value):
                    return value
                raise self._refuse(value, "an IANA timezone name")
            case SettingType.STRING | SettingType.PATH:
                if isinstance(value, str) and value:
                    return value
                raise self._refuse(value, "text")
            case _:
                if isinstance(value, int) and not isinstance(value, bool):
                    return self._in_range(value)
                raise self._refuse(value, "a whole number")

    def _in_range[Number: (int, float)](self, value: Number) -> Number:
        if self.zero_means_off and value == 0:
            return value
        if self.min is not None and value < self.min:
            raise self._refuse(value, f"at least {self.min:g}")
        if self.max is not None and value > self.max:
            raise self._refuse(value, f"at most {self.max:g}")
        return value

    def _refuse(self, value: object, expected: str) -> SettingValueError:
        return SettingValueError(
            f"{self.name} cannot be {value!r}: it must be {expected} (allowed: {self.spec_range})."
        )

    @property
    def is_whole_number(self) -> bool:
        return self.type in _WHOLE_NUMBERS


class Setting(Definition):
    """A governed setting (Appendix A). `project_types` limits it to those project types."""

    scope: Scope
    project_types: tuple[str, ...] = ()


class OperationalSetting(Definition):
    """An environment variable read at start (NFR-7). Not changed through the catalog."""


class Constraint(BaseModel):
    """A rule between settings, checked when a bundle of changes is validated (GOV-1)."""

    model_config = ConfigDict(frozen=True)

    id: str
    settings: tuple[str, ...]
    spec: str


class SettingsRegistry:
    def __init__(
        self,
        settings: dict[str, Setting],
        constraints: tuple[Constraint, ...],
        operational: dict[str, OperationalSetting],
    ) -> None:
        self.settings = settings
        self.constraints = constraints
        self.operational = operational

    def get(self, name: str) -> Setting:
        """The setting called `name`. An unknown name is refused, naming the closest (GOV-1)."""
        try:
            return self.settings[name]
        except KeyError:
            matches = difflib.get_close_matches(name, self.settings, n=1)
            raise UnknownSettingError(name, matches[0] if matches else None) from None


def _is_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _is_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


@cache
def load_registry() -> SettingsRegistry:
    """Load the registry from the packaged data file."""
    text = resources.files(__package__).joinpath("registry.toml").read_text(encoding="utf-8")
    data = tomllib.loads(text)
    settings = {
        name: Setting.model_validate({"name": name, **fields})
        for name, fields in data["settings"].items()
    }
    operational = {
        name: OperationalSetting.model_validate({"name": name, **fields})
        for name, fields in data["operational"].items()
    }
    constraints = tuple(Constraint.model_validate(item) for item in data["constraints"])
    return SettingsRegistry(settings, constraints, operational)
