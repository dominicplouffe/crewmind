"""Fetch the local embedding model into the package (MEM-2).

The model is shipped inside the crewmind package and the Docker image, so memory works
offline from the first start. It is too large for the source repository, so the package
build, the image build and a developer in a source checkout each run:

    python -m crewmind.domain.memory.fetch_model
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any

from crewmind.domain.memory.engine import EMBEDDING_MODEL, shipped_model_directory

KEYWORD_MODEL = "Qdrant/bm25"


def main() -> int:
    target = shipped_model_directory()
    target.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    fastembed: Any = importlib.import_module("fastembed")
    fastembed.TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=str(target))
    fastembed.SparseTextEmbedding(model_name=KEYWORD_MODEL, cache_dir=str(target))
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) // 1_000_000
    print(f"The embedding model is in {target} ({size} MB).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
