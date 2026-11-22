import re
import subprocess
import sys

number, title = sys.argv[1], sys.argv[2]
import glob
import os

for old in glob.glob(f"src/crewmind/storage/migrations/versions/{sys.argv[1]}_*.py"):
    os.remove(old)
body = subprocess.run(
    ["uv", "run", "-q", "python", "scripts/dev/gen_migration.py"], capture_output=True, text=True
).stdout
body = body.replace(
    "crewmind.storage.models.base.UtcDateTime(timezone=True)", "sa.DateTime(timezone=True)"
)
body = "\n".join(l for l in body.split("\n") if "###" not in l).rstrip()
prev = f"{int(number) - 1:04d}"
slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
text = f'''"""{title}

Revision: {number}
Revises: {prev}
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "{number}"
down_revision: str | None = "{prev}"


def upgrade() -> None:
{body}
'''
path = f"src/crewmind/storage/migrations/versions/{number}_{slug}.py"
open(path, "w").write(text)
subprocess.run(["uv", "run", "-q", "ruff", "format", "-q", path])
subprocess.run(["uv", "run", "-q", "ruff", "check", "-q", "--fix", path])
print(path)
