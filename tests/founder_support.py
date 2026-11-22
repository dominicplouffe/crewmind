"""Helpers for tests that drive the Founder with a scripted model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from crewmind.domain.founder import tree
from crewmind.domain.rehearsal import operations as rehearsal
from crewmind.domain.secrets.store import ensure_master_key
from tests.support import Actor, App

ACCEPTANCE = Path(__file__).parents[1] / "acceptance"
GOAL = (ACCEPTANCE / "reference-goal.md").read_text(encoding="utf-8")
BRIEF = (ACCEPTANCE / "raw-brief.md").read_text(encoding="utf-8")
DOCUMENT = (ACCEPTANCE / "grill-document.md").read_text(encoding="utf-8")
ROLE_WORDS = "I will answer questions about the valley but I do not have time to write any of it."

SPEC: dict[str, Any] = {
    "name": "Hollin Valley bird guide",
    "goal": GOAL,
    "type": "deliver",
    "teams": [
        {"name": "Entries", "role": "researcher", "members": ["Rey", "Sol"]},
        {"name": "Plan review", "role": "plan-adversary", "members": ["Ada"]},
    ],
}
DECISIONS: dict[str, dict[str, Any]] = {
    decision.key: {"value": f"The Founder's recommendation for {decision.key}."}
    for decision in tree.TREE
}
FIRST = {
    "text": "A first usable guide to five birds exists.",
    "success_test": "A walker can name each of the five birds from its entry.",
}


def grades(name: str) -> list[dict[str, Any]]:
    return json.loads((ACCEPTANCE / f"{name}.grades.json").read_text(encoding="utf-8"))["grades"]


def tool(tool_name: str, /, **arguments: Any) -> dict[str, Any]:
    return {"tools": [{"name": tool_name, "arguments": arguments}]}


def question(settles: str, *, options: list[str] | None = None, **more: Any) -> dict[str, Any]:
    return {
        "settles": settles,
        "text": f"Shall I settle {settles} as I recommend?",
        "options": options or ["Yes, as recommended", "No, something else"],
        "recommended": 0,
        "changes": "It changes what the draft says.",
        **more,
    }


def propose(**changes: Any) -> dict[str, Any]:
    spec = {**SPEC, **changes.pop("spec", {})}
    return tool(
        "propose_spec",
        spec=spec,
        decisions=changes.pop("decisions", DECISIONS),
        first_requirement=FIRST,
        **changes,
    )


def script(app: App, *turns: dict[str, Any], graded: str = "reference-goal") -> None:
    """Give the Founder its script. One list plays through the whole conversation."""
    app.script("founder/draft", *turns)
    app.script("founder/grade", {"text": json.dumps(grades(graded))})


async def credential(app: App, owner: Actor, name: str) -> None:
    ensure_master_key(app.runtime.config.master_key_file)
    await app.ok("credentials.add", owner, name=name, provider="mock", key=f"sk-{name}-0123456789")


@pytest.fixture
def quick_rehearsal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rehearsal that reports a clean walk at once. The drill itself is tested in
    `tests/attack/test_rehearsal.py`; these tests are about the Founder."""

    async def drill(_: Any, spec: Any) -> dict[str, Any]:
        return {
            "refusal": None,
            "reached": True,
            "stalled": False,
            "missing": [],
            "waits": [],
            "jumps": [],
            "refusals": [],
            "seats": [],
            "settings": {},
            "events": [],
            "started_at": "2030-01-07T09:00:00+00:00",
        }

    monkeypatch.setattr(rehearsal, "drill", drill)
