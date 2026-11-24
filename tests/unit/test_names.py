"""Names used before ADR-0008 stay out of the repository (NFR-21)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OLD = re.compile("crew(?!ai)", re.IGNORECASE)

# This file names what it looks for.
KEEPS_OLD_NAMES = ("tests/unit/test_names.py",)


def _tracked() -> list[str]:
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [name for name in listed.decode().split("\0") if name]


def test_NFR_21_the_old_product_and_concept_names_do_not_come_back() -> None:
    """NFR-21: the product is nightsquad and the library's ready-made job is a squad
    (ADR-0008). No tracked file's name or text uses an earlier name."""
    found: list[str] = []
    for name in _tracked():
        if name.startswith(KEEPS_OLD_NAMES):
            continue
        if OLD.search(name):
            found.append(f"{name}: file name")
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if OLD.search(line):
                found.append(f"{name}:{number}: {line.strip()[:120]}")
    assert found == [], "\n".join(found)
