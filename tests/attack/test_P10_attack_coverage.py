"""Every rule ships with an attack (P10)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from crewmind.catalog import Rule, rules
from crewmind.catalog.registry import load_domain_modules
from crewmind.runtime import Runtime
from tests.attack.harness import Attacker, assert_refused, attacked_rules, rules_without_attack
from tests.support import REFUSED_NAME, Greeter, api_client_factory, sample_api, sample_catalog


def test_P10_every_registered_rule_has_an_attack_test() -> None:
    """P10: a rule in the registry with no attack test in tests/attack fails the suite."""
    load_domain_modules()
    assert rules_without_attack(rules, attacked_rules()) == []


def test_P10_a_rule_without_an_attack_is_reported(tmp_path: Path) -> None:
    """P10: the coverage check names each rule that lacks an attack."""
    (tmp_path / "test_sample.py").write_text(
        "import pytest\n\n"
        '@pytest.mark.attack("SAMPLE-1")\n'
        "async def test_SAMPLE_1_is_attacked():\n    pass\n\n"
        '@pytest.mark.attack("SAMPLE-3")\n'
        "def helper_not_a_test():\n    pass\n",
        encoding="utf-8",
    )
    registered = [Rule("SAMPLE-1", "First."), Rule("SAMPLE-2", "Second."), Rule("SAMPLE-3", "3.")]
    assert attacked_rules(tmp_path) == {"SAMPLE-1"}
    assert rules_without_attack(registered, attacked_rules(tmp_path)) == ["SAMPLE-2", "SAMPLE-3"]


async def test_P10_the_harness_attacks_through_the_public_api(runtime: Runtime) -> None:
    """P10, IF-1.4: the attacker calls the real API and the refusal is checked by rule and code."""
    async with api_client_factory(sample_api(runtime, sample_catalog(Greeter())))() as client:
        attacker = Attacker(client, {"forged": "not-a-real-token"})
        forged = await attacker.call(
            "POST", "/v1/sample/greet", acting_as="forged", json={"name": "ada"}
        )
        assert forged.request.headers["Authorization"] == "Bearer not-a-real-token"
        assert forged.status_code == 401
        response = await attacker.call(
            "POST", "/v1/sample/greet", acting_as=None, json={"name": REFUSED_NAME}
        )
        envelope = assert_refused(response, rule="SAMPLE-1", code="sample_refused")
        assert envelope.hint == "Greet someone else."
        allowed = await attacker.call(
            "POST", "/v1/sample/greet", acting_as=None, json={"name": "ada"}
        )
        with pytest.raises(AssertionError):
            assert_refused(allowed, rule="SAMPLE-1")
    assert isinstance(client, httpx.AsyncClient)
