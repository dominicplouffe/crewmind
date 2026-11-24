"""Attacks on runs paid by a command-line agent's login (LLM-8, P9, INV-8)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select

from crewmind.domain.models.service import KIND_KEY, KIND_LOGIN
from crewmind.storage.models import LedgerLine, ModelCredential, Run
from tests.attack.harness import assert_refused
from tests.support import App, live_run, running_project


async def pay_with(app: App, run_id: str, owner_id: str, kind: str) -> None:
    """The run is paid by a credential of this kind, as the lease would have chosen it."""
    async with app.runtime.sessions() as session, session.begin():
        credential = ModelCredential(
            name=f"{kind}-credential", provider="mock", kind=kind, base_url=None,
            owner_id=owner_id, state="active", created_at=app.runtime.clock(),
        )  # fmt: skip
        session.add(credential)
        await session.flush()
        run = await session.get(Run, run_id)
        assert run is not None
        run.credential_id = credential.id


async def post(app: App, path: str, token: str, body: dict[str, Any]) -> Any:
    async with app.client() as client:
        return await client.post(path, json=body, headers={"Authorization": f"Bearer {token}"})


async def ledger_lines(app: App, project: str) -> int:
    async with app.runtime.sessions() as session:
        found = await session.scalar(
            select(func.count()).select_from(LedgerLine).where(LedgerLine.project_id == project)
        )
        return int(found or 0)


COMPLETION = {"system": "s", "messages": [{"role": "user", "content": "go"}], "tools": []}
UNDER_REPORTED = {"usage": {"input": 1, "output": 1}, "text": "cheap"}


@pytest.mark.attack("LLM-8")
async def test_LLM_8_the_gateway_never_calls_a_model_with_a_login(app: App) -> None:
    """LLM-8, P3: a run paid by a command-line agent's login asks the gateway for a model
    call anyway. The gateway refuses, never reveals the login, and books nothing."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    run = await live_run(app, project)
    await pay_with(app, run.run_id, owner.person_id, KIND_LOGIN)
    app.script("*", {"text": "should never be asked"})

    refused = await post(app, "/gateway/v1/complete", run.token, COMPLETION)
    assert_refused(refused, rule="LLM-8", code="login_credential")
    assert await ledger_lines(app, project) == 0


@pytest.mark.attack("LLM-8")
@pytest.mark.parametrize("kind", [None, KIND_KEY])
async def test_LLM_8_a_metered_run_cannot_report_its_own_usage(app: App, kind: str | None) -> None:
    """LLM-8, P9, INV-8: a run the gateway meters (unpaid, or paid by an API key) reports a
    tiny usage of its own, to make its spend look smaller. The report is refused and
    nothing is booked: only a login run reports, because only it calls its provider."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    run = await live_run(app, project)
    if kind is not None:
        await pay_with(app, run.run_id, owner.person_id, kind)

    refused = await post(app, "/gateway/v1/report", run.token, UNDER_REPORTED)
    assert_refused(refused, rule="LLM-8", code="not_a_login_run")
    assert await ledger_lines(app, project) == 0


@pytest.mark.attack("LLM-8")
async def test_LLM_8_a_report_needs_a_live_run_token(app: App) -> None:
    """LLM-8, INV-4: a report with no token, or a made-up one, is refused before anything
    is read or booked."""
    owner = await app.person("owner@example.com")
    project = await running_project(app, owner)
    for token in ("", "not-a-run-token"):
        refused = await post(app, "/gateway/v1/report", token, UNDER_REPORTED)
        assert refused.status_code == 401, refused.text
    assert await ledger_lines(app, project) == 0
