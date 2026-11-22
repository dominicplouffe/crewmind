"""Rehearsing a spec or a project: the zero-token fire drill (RHS-1 to RHS-4)."""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
from typing import Any

from sqlalchemy import func, select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal
from crewmind.catalog.rules import Rule, rules
from crewmind.domain.execution.model import RunKind, RunState
from crewmind.domain.library import transfer
from crewmind.domain.library.spec import ProjectSpec
from crewmind.domain.projects.access import view_of
from crewmind.domain.projects.operations import ProjectRef
from crewmind.domain.rehearsal.report import History, RehearsalReport, build
from crewmind.domain.settings.registry import Scope
from crewmind.domain.settings.service import INSTALL_SUBJECT, Subject
from crewmind.services import services_of
from crewmind.storage.models import LedgerLine, Run

RHS_1 = rules.register(
    Rule(
        "RHS-1",
        "A rehearsal runs on a database of its own: no tokens, no network, no credentials.",
    )
)

DRILL = "crewmind.domain.rehearsal.drill"
HISTORY_RUNS_LEAST = 10  # GOV-4: history counts once at least 10 runs exist
HISTORY_RUNS_READ = 500
"""The newest finished runs a median is taken from."""


async def history(context: Context) -> History:
    """What this install's finished work runs cost and how long they took (GOV-4)."""
    rows = (
        await context.session.execute(
            select(Run.id, Run.started_at, Run.ended_at)
            .where(Run.kind == RunKind.WORK, Run.state == RunState.FINISHED)
            .order_by(Run.ended_at.desc())
            .limit(HISTORY_RUNS_READ)
        )
    ).all()
    if len(rows) < HISTORY_RUNS_LEAST:
        return History(runs=len(rows))
    tokens = dict(
        (
            await context.session.execute(
                select(LedgerLine.run_id, func.sum(LedgerLine.counted))
                .where(LedgerLine.run_id.in_([row.id for row in rows]))
                .group_by(LedgerLine.run_id)
            )
        ).all()
    )
    seconds = [
        (row.ended_at - row.started_at).total_seconds()
        for row in rows
        if row.started_at and row.ended_at
    ]
    return History(
        runs=len(rows),
        median_tokens=int(statistics.median(int(tokens.get(row.id) or 0) for row in rows)),
        median_seconds=statistics.median(seconds) if seconds else None,
    )


async def drill(context: Context, spec: ProjectSpec) -> dict[str, Any]:
    """Run the drill in a process of its own. It is given the spec and nothing else: no
    database address, no key file, no credential (RHS-1)."""
    limit = int(
        await services_of(context).settings.get(
            context.session, Subject(Scope.INSTALL, INSTALL_SUBJECT), "rehearsal.max_seconds"
        )
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-m",
        DRILL,
        env={"PYTHONPATH": os.pathsep.join(sys.path), "PATH": os.environ.get("PATH", "")},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    document = spec.model_dump_json().encode()
    try:
        out, _ = await asyncio.wait_for(process.communicate(document), timeout=limit)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise Refusal(
            "rehearsal_too_long",
            f"The rehearsal did not finish within {limit} seconds and was stopped.",
            rule=RHS_1.id,
            hint="An admin can raise `rehearsal.max_seconds`.",
        ) from None
    if process.returncode != 0:
        raise Refusal(
            "rehearsal_failed",
            "The rehearsal stopped with an error before it could report.",
            rule=RHS_1.id,
        )
    return json.loads(out)


async def rehearse(context: Context, spec: ProjectSpec) -> RehearsalReport:
    problems = await transfer.check(context, spec)
    if problems:
        found: dict[str, Any] = {
            "refusal": {"message": " ".join(problems)},
            "reached": False,
            "missing": [],
            "waits": [],
            "refusals": [],
            "seats": [],
            "settings": {},
            "events": [],
            "started_at": context.now.isoformat(),
        }
        return build(found, spec.type, History())
    found = await drill(context, spec)
    # The drill's own install has no credentials. What is missing is this install's answer.
    found["missing"] = await transfer.missing_setup(context, spec)
    return build(found, spec.type, await history(context))


@operation(
    "specs.rehearse",
    summary="Rehearse a project spec: a fire drill that spends no tokens.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def rehearse_spec(context: Context, payload: ProjectSpec) -> RehearsalReport:
    """RHS-1 to RHS-4: the real rules, dispatcher and scheduler run the spec with a crew
    in code, on a database made for the drill. Nothing is created here."""
    return await rehearse(context, payload)


@operation(
    "projects.rehearse",
    summary="Rehearse this project as it is set up now, without spending tokens.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
    slash_command="/rehearse",
)
async def rehearse_project(context: Context, payload: ProjectRef) -> RehearsalReport:
    """RHS-4: the project's own spec, as an export would write it, is what is rehearsed."""
    spec = await transfer.export(context, view_of(context).project)
    return await rehearse(context, spec)
