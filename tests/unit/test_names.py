"""The product's old names stay out of the repository (NFR-21, ADR-0011)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OLD = re.compile("crew", re.IGNORECASE)

# Where an old name is the point: history written under it, and the code and tests that
# carry an install or a file from before the rename.
KEEPS_OLD_NAMES = (
    "docs/spec/CHANGELOG.md",
    "docs/decisions/ADR-0008-project-name.md",
    "docs/decisions/ADR-0011-renamed-nightsquad.md",
    "docs/phases/",
    "docs/rename-plan.md",
    "src/nightsquad/storage/migrations/versions/",
    "src/nightsquad/domain/library/legacy.py",
    "src/nightsquad/domain/install/old_name.py",
    "deploy/_old_install.sh",
    "tests/unit/test_storage.py",
    "tests/unit/test_names.py",
    "tests/attack/test_library.py",
)


def _tracked() -> list[str]:
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [name for name in listed.decode().split("\0") if name]


def test_NFR_21_the_old_product_and_concept_names_do_not_come_back() -> None:
    """NFR-21: the product is nightsquad and the library's ready-made job is a squad. No
    tracked file name or text file outside the history and the rename's own bridges uses
    the old names."""
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
