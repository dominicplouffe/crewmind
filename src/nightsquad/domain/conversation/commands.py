"""Slash commands typed in the chat, and the small operations some of them name (CHAT-5,
CHAT-13, GOV-1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from nightsquad.catalog.caller import Authority
from nightsquad.catalog.define import Empty, operation
from nightsquad.catalog.execute import Context
from nightsquad.catalog.operation import Reversibility
from nightsquad.catalog.registry import catalog
from nightsquad.domain.projects.operations import ProjectRef

SLASH_REASON = "Changed with a slash command in the project chat."


class CommandInput(ProjectRef):
    text: str = Field(description="The command line, starting with /.")


class CommandResult(BaseModel):
    command: str
    operation: str
    result: dict[str, Any]


class CommandHelp(BaseModel):
    commands: dict[str, str]
    later: list[str] = Field(description="Commands that arrive in later phases.")


class QualityInput(ProjectRef):
    level: Literal["fast", "balanced", "best"] | None = Field(
        default=None, description="fast, balanced or best. Leave out to see the current choice."
    )


class BrevityInput(BaseModel):
    level: Literal["short", "normal", "detailed"] = Field(description="short, normal or detailed.")


class BudgetInput(ProjectRef):
    tokens: int | None = Field(default=None, description="A new token budget. Leave out to see it.")


LATER = ["/desk"]


@operation(
    "chat.command",
    summary="Run a slash command typed in the project chat, such as /hold or /do.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.REVERSIBLE,
)
async def command(context: Context, payload: CommandInput) -> CommandResult:
    """CHAT-5, IF-1.2: a slash command is the operation it names, run as the person who
    typed it, with that operation's own authority check."""
    from nightsquad.surfaces.slash.adapter import parse

    target, values = parse(catalog, payload.project_id, payload.text)
    result = await context.executor.call(context, target, values)
    return CommandResult(
        command=payload.text.split(" ", 1)[0],
        operation=target.name,
        result=result.model_dump(mode="json"),
    )


@operation(
    "chat.help",
    summary="List the slash commands and what each does.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    slash_command="/help",
)
async def help_(context: Context, payload: Empty) -> CommandHelp:
    from nightsquad.surfaces.slash.adapter import commands

    return CommandHelp(
        commands={name: target.summary for name, target in sorted(commands(catalog).items())},
        later=LATER,
    )


@operation(
    "chat.quality",
    summary="Show or set the project's quality: fast, balanced or best.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/quality",
)
async def quality(context: Context, payload: QualityInput) -> BaseModel:
    """LLM-3, GOV-1: `/quality best` is a settings change by the chairman, with the reason
    recorded; `/quality` alone shows what each seat runs on."""
    if payload.level is not None:
        change = catalog.get("settings.change_project")
        await context.executor.call(
            context,
            change,
            change.input(
                project_id=payload.project_id,
                changes={"quality": payload.level},
                reason=SLASH_REASON,
            ),
        )
    show = catalog.get("models.show")
    return await context.executor.call(context, show, show.input(project_id=payload.project_id))


@operation(
    "chat.brevity",
    summary="Set how long agents' replies to you are: short, normal or detailed.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/brevity",
)
async def brevity(context: Context, payload: BrevityInput) -> BaseModel:
    """CHAT-13: brevity is each person's own preference."""
    change = catalog.get("settings.change_mine")
    return await context.executor.call(
        context, change, change.input(changes={"chat.brevity": payload.level})
    )


@operation(
    "budget.command",
    summary="Show the token budget, or set a new one.",
    authority=Authority.PROJECT_OBSERVER,
    reversibility=Reversibility.REVERSIBLE,
    slash_command="/budget",
)
async def budget(context: Context, payload: BudgetInput) -> BaseModel:
    """GOV-1, GOV-2: `/budget 30000000` is a settings change by the chairman; `/budget`
    alone shows used, remaining and the wall."""
    if payload.tokens is not None:
        change = catalog.get("settings.change_project")
        await context.executor.call(
            context,
            change,
            change.input(
                project_id=payload.project_id,
                changes={"budget.tokens": payload.tokens},
                reason=SLASH_REASON,
            ),
        )
        await context.session.flush()
    show = catalog.get("budget.show")
    return await context.executor.call(context, show, show.input(project_id=payload.project_id))
