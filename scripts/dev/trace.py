"""Map requirement ids to the tests that cite them (name or docstring)."""

import ast
import collections
import csv
import re
from pathlib import Path

ids = [r["id"] for r in csv.DictReader(open("docs/traceability.csv", newline=""))]
idset = set(ids)
found = collections.defaultdict(list)
for path in sorted(Path("tests").rglob("test_*.py")):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            text = node.name + " " + (ast.get_docstring(node) or "")
            cited = set(re.findall(r"\b(?:[A-Z]{1,4}-\d+(?:\.\d+)?|P\d+)\b", text))
            m = re.match(r"test_([A-Z]+)_(\d+)(?:_(\d+))?_", node.name)
            if m:
                a = f"{m.group(1)}-{m.group(2)}"
                cited.add(a)
                if m.group(3):
                    cited.add(f"{a}.{m.group(3)}")
            for c in cited & idset:
                found[c].append(f"{path.as_posix()}::{node.name}")
if __name__ == "__main__":
    rows = list(csv.DictReader(open("docs/traceability.csv", newline="")))
    for r in rows:
        if r["phase"] == "2":
            print(r["id"], len(found[r["id"]]), r["status"], "|", r["notes"][:60])
