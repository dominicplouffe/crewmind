"""The shape of what the Founder hands in: reading it generously, and saying everything
that is wrong with it at once (FND-1, FND-2).

A model that puts a field one level too high or too low has made no decision the rules
care about, so the input is put right instead of refused. Each refusal costs the chairman
a whole model call of waiting.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import ValidationError

PROBLEMS_SHOWN = 12
"""How many problems of one refused input are named at once: enough to fix it in one go."""


def problems_of(error: ValidationError) -> str:
    """Every problem of a refused input, each with the field it is in. Naming only the
    first would cost the model one call per mistake (FND-1)."""
    found = error.errors()
    named = [
        f"{'.'.join(str(part) for part in problem['loc']) or 'the input'}: {problem['msg']}"
        for problem in found[:PROBLEMS_SHOWN]
    ]
    more = len(found) - len(named)
    return "; ".join(named) + (f"; and {more} more" if more > 0 else "") + "."


def without_references(schema: dict[str, Any]) -> dict[str, Any]:
    """A JSON schema with every `$ref` replaced by what it points to. Some models do not
    follow references in a tool's schema, and would see no fields at all."""
    definitions: dict[str, Any] = schema.get("$defs", {})

    def resolved(node: Any) -> Any:
        if isinstance(node, list):
            return [resolved(item) for item in cast(list[Any], node)]
        if not isinstance(node, dict):
            return node
        fields = cast(dict[str, Any], node)
        if "$ref" in fields:
            target = definitions[str(fields["$ref"]).rsplit("/", 1)[-1]]
            rest = {key: value for key, value in fields.items() if key != "$ref"}
            return resolved({**target, **rest})
        return {key: resolved(value) for key, value in fields.items() if key != "$defs"}

    return resolved(schema)


BESIDE_THE_SPEC = ("decisions", "reasons", "first_requirement", "first_bets")
"""What `propose_spec` takes beside the spec itself."""


def arranged(arguments: dict[str, Any], spec_fields: set[str]) -> dict[str, Any]:
    """The arguments of `propose_spec` with each field where it belongs. A spec's fields
    given beside `spec` are moved into it; what belongs beside the spec and was put inside
    it is moved out. Nothing is added and nothing is dropped."""
    given = dict(arguments)
    target = "changes" if "changes" in given and "spec" not in given else "spec"
    inner = given.get(target)
    spec: dict[str, Any] = dict(cast(dict[str, Any], inner)) if isinstance(inner, dict) else {}
    for name in [name for name in given if name in spec_fields]:
        spec.setdefault(name, given.pop(name))
    for name in BESIDE_THE_SPEC:
        if name in spec and name not in spec_fields:
            given.setdefault(name, spec.pop(name))
    if spec or target in given:
        given[target] = spec
    decisions = given.get("decisions")
    if isinstance(decisions, dict):
        # A decision given as its bare value is the same decision.
        given["decisions"] = {
            key: {"value": value} if isinstance(value, str) else value
            for key, value in cast(dict[str, Any], decisions).items()
        }
    return given


def changed(current: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """A spec with some of its fields replaced. A field set to null is removed."""
    merged = {**current, **changes}
    return {name: value for name, value in merged.items() if value is not None}
