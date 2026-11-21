"""The attack-test harness (P10).

Every enforced rule ships with a test that tries to break it through the public API, the
way an agent would. An attack test is marked with the rule it attacks:

    @pytest.mark.attack("GOV-3")
    async def test_GOV_3_wall_refuses_a_lease_with_a_forged_token(...): ...

`rules_without_attack` is the coverage check: it fails the suite when a registered rule
has no attack test.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import httpx

from crewmind.catalog import ErrorEnvelope, Rule

ATTACK_DIRECTORY = Path(__file__).parent


def attacked_rules(directory: Path = ATTACK_DIRECTORY) -> set[str]:
    """The rule ids named by `pytest.mark.attack(...)` on test functions under `directory`."""
    found: set[str] = set()
    for path in sorted(directory.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not decorator.args:
                    continue
                target, rule = decorator.func, decorator.args[0]
                is_attack = isinstance(target, ast.Attribute) and target.attr == "attack"
                if is_attack and isinstance(rule, ast.Constant) and isinstance(rule.value, str):
                    found.add(rule.value)
    return found


def rules_without_attack(rules: Iterable[Rule], attacked: set[str]) -> list[str]:
    """The ids of registered rules that no attack test names (P10)."""
    return sorted(rule.id for rule in rules if rule.id not in attacked)


def assert_refused(
    response: httpx.Response, *, rule: str, code: str | None = None, status: int = 403
) -> ErrorEnvelope:
    """Assert the API refused the call under `rule`, with the shared envelope (IF-1.4)."""
    assert response.status_code == status, response.text
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.rule == rule, envelope
    if code is not None:
        assert envelope.code == code, envelope
    assert envelope.message, "a refusal states its rule in a plain sentence (IF-1.4)"
    return envelope


class Attacker:
    """Calls the public API as an agent trying to get around a rule would (P10).

    `credentials` maps a label to a bearer token: the attacker's own, a foreign one, a
    forged one. `call` sends a request under the chosen label, or with no credential.
    """

    def __init__(self, client: httpx.AsyncClient, credentials: Mapping[str, str]) -> None:
        self._client = client
        self._credentials = dict(credentials)

    async def call(
        self,
        method: str,
        path: str,
        *,
        acting_as: str | None,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if acting_as is not None:
            headers["Authorization"] = f"Bearer {self._credentials[acting_as]}"
        return await self._client.request(method, path, json=json, params=params, headers=headers)
