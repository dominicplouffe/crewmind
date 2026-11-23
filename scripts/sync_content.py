"""Copy the library in `content/` into the package the server ships (LIB-3)."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).parents[1]
PACKAGED = ROOT / "src" / "crewmind" / "content" / "library"

if __name__ == "__main__":
    for folder in ("roles", "crews", "mcp-servers"):
        shutil.rmtree(PACKAGED / folder, ignore_errors=True)
        shutil.copytree(ROOT / "content" / folder, PACKAGED / folder)
        print(f"{folder}: {len(list((PACKAGED / folder).glob('*.json')))} files")
    doctrine = PACKAGED.parent / "doctrine"
    doctrine.mkdir(exist_ok=True)
    for source in ("doctrine/design-doctrine.md", "goal-grammar/goal-grammar.md"):
        shutil.copy(ROOT / "content" / source, doctrine / Path(source).name)
    print("doctrine: 2 files")
