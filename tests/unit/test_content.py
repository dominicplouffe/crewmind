"""The packaged library is the one in `content/` (LIB-3)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
PACKAGED = ROOT / "src" / "crewmind" / "content" / "library"


def test_LIB_3_the_packaged_library_is_a_copy_of_the_content_folder() -> None:
    """LIB-3: roles and crews are edited in `content/` and shipped from the package. The
    two must not drift: run `scripts/sync_content.py` after editing."""
    for folder in ("roles", "crews"):
        source = {path.name: path.read_bytes() for path in (ROOT / "content" / folder).glob("*")}
        shipped = {path.name: path.read_bytes() for path in (PACKAGED / folder).glob("*")}
        assert source == shipped, f"content/{folder} and the packaged copy differ"
    for source in ("doctrine/design-doctrine.md", "goal-grammar/goal-grammar.md"):
        shipped = PACKAGED.parent / "doctrine" / Path(source).name
        assert (ROOT / "content" / source).read_bytes() == shipped.read_bytes(), source
