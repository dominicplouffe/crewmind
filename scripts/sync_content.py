"""Copy the library in `content/` into the package the server ships (LIB-3)."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).parents[1]
PACKAGED = ROOT / "src" / "crewmind" / "content" / "library"

if __name__ == "__main__":
    for folder in ("roles", "crews"):
        shutil.rmtree(PACKAGED / folder, ignore_errors=True)
        shutil.copytree(ROOT / "content" / folder, PACKAGED / folder)
        print(f"{folder}: {len(list((PACKAGED / folder).glob('*.json')))} files")
