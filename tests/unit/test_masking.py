"""The masker: every form of a given secret's value becomes [secret: NAME] (CON-8)."""

from __future__ import annotations

import base64
from urllib.parse import quote, quote_plus

from hypothesis import given
from hypothesis import strategies as st

from crewmind.domain.connections.delivery import Given, Masker

VALUE = "p@ss word/+=&?unguessable"


def masker(*values: tuple[str, str], variable: str | None = None) -> Masker:
    items = [Given(name, name, name.upper(), "", value, True, False) for name, value in values]
    if variable is not None:
        items.append(Given("v", "region", "REGION", "", variable, False, False))
    return Masker.of(items)


def test_CON_8_every_encoding_of_a_value_is_masked() -> None:
    """CON-8: as written, base64 standard and URL-safe with or without padding, and
    URL-encoded both ways; a variable is never masked."""
    mask = masker(("wordpress", VALUE), variable="ca-east")
    raw = VALUE.encode()
    for form in (
        VALUE,
        base64.b64encode(raw).decode(),
        base64.urlsafe_b64encode(raw).decode().rstrip("="),
        quote(VALUE, safe=""),
        quote_plus(VALUE),
    ):
        assert mask.text(f"before {form} after") == "before [secret: wordpress] after"
    assert mask.text("region ca-east") == "region ca-east"
    assert not masker(variable="ca-east")


def test_CON_8_files_and_nested_data_are_masked() -> None:
    """CON-8: JSON-like data at any depth, text files, and the raw value in a binary file."""
    mask = masker(("key", VALUE))
    assert mask.data({"a": [VALUE, {"b": f"x{VALUE}"}], "n": 3}) == {
        "a": ["[secret: key]", {"b": "x[secret: key]"}],
        "n": 3,
    }
    assert mask.bytes(f"line {VALUE}\n".encode()) == (b"line [secret: key]\n", ["key"])
    binary = b"\xff\xfe" + VALUE.encode()
    assert mask.bytes(binary) == (b"\xff\xfe[secret: key]", ["key"])
    assert mask.bytes(b"nothing here") == (b"nothing here", [])


@given(st.text(min_size=8, max_size=40).filter(lambda value: value not in "[secret: s]"))
def test_CON_8_no_value_survives_masking(value: str) -> None:
    """CON-8: whatever the value, it does not appear in the masked text."""
    mask = masker(("s", value))
    assert value not in mask.text(f"<{value}>{value}")
