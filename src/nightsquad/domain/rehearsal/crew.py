"""The rehearsal's crew: a competent agent in code, in place of a model (RHS-1).

Each run it reads the plan and the board through the agent's own tools, then takes the
next step a competent agent in that seat would take. It reads nothing from the spec but
the roster, so no text or command in a spec is ever acted on."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nightsquad.gateway.mock import MockProvider
from nightsquad.gateway.protocol import CompletionRequest, CompletionResponse, TokenUsage, ToolCall

PLAN, BOARD = "agent_plan", "agent_board"
TURNS_MOST = 12
"""A run of the rehearsal crew ends after this many steps, whatever the state."""
NO_USAGE = TokenUsage()

Action = tuple[str, dict[str, Any]]


@dataclass
class Seen:
    """What one run has read so far, and what it has done."""

    plan: dict[str, Any] = field(default_factory=dict[str, Any])
    board: dict[str, Any] = field(default_factory=dict[str, Any])
    done: list[Action] = field(default_factory=list[Action])
    refused: bool = False


def _seen(request: CompletionRequest) -> Seen:
    seen = Seen()
    names: dict[str, ToolCall] = {}
    for turn in request.messages:
        for call in turn.tool_calls:
            names[call.id] = call
        if turn.role != "tool" or turn.tool_call_id not in names:
            continue
        call = names[turn.tool_call_id]
        try:
            result = json.loads(turn.content)
        except ValueError:
            result = {}
        if not isinstance(result, dict):
            continue
        if call.name == PLAN:
            seen.plan = result
        elif call.name == BOARD:
            seen.board = result
        else:
            seen.done.append((call.name, call.arguments))
            if "code" in result and "kind" in result:
                seen.refused = True
    return seen


@dataclass(frozen=True)
class Roster:
    """Who is who in the drill, from the spec's roster."""

    type: str
    worker_teams: list[str]
    seat_team: dict[str, str]
    reviewers: set[str]
    ceo_accepts: bool


class DrillCrew(MockProvider):
    name = "mock"

    def __init__(self, roster: Roster) -> None:
        super().__init__(None)
        self.roster = roster
        self.calls = 0
        self.tasked: set[tuple[str, int, str]] = set()
        """Tasks the CEO has created: what each serves, and for which team."""
        self.found: set[int] = set()

    def has_script(self, seat_name: str, run_kind: str) -> bool:
        return True

    async def complete(
        self,
        request: CompletionRequest,
        *,
        seat_name: str,
        run_kind: str,
        calls_so_far: int,
        on_delta: Callable[[str], None] | None = None,
        run_id: str | None = None,
    ) -> CompletionResponse:
        self.calls += 1
        if run_kind != "work":
            return self._say("The rehearsal crew does not chat.", on_delta)
        seen = _seen(request)
        if not seen.plan and not seen.board and calls_so_far == 0:
            return self._do([(PLAN, {}), (BOARD, {})], calls_so_far)
        if seen.refused or calls_so_far >= TURNS_MOST:
            return self._say("Stopping here.", on_delta)
        whole = self._whole_job(seat_name, seen)
        if whole:
            return self._do(whole, calls_so_far)
        action = self._next(seat_name, seen)
        if action is None:
            return self._say("Nothing more to do in this run.", on_delta)
        return self._do([action, (PLAN, {}), (BOARD, {})], calls_so_far)

    def _say(self, text: str, on_delta: Callable[[str], None] | None) -> CompletionResponse:
        if on_delta is not None:
            on_delta(text)
        return CompletionResponse(text=text, usage=NO_USAGE)

    def _do(self, actions: list[Action], turn: int) -> CompletionResponse:
        calls = [
            ToolCall(id=f"call_{turn}_{index}", name=name, arguments=arguments)
            for index, (name, arguments) in enumerate(actions)
        ]
        return CompletionResponse(tool_calls=calls, usage=NO_USAGE)

    def _whole_job(self, seat: str, seen: Seen) -> list[Action]:
        """A worker with a task to take does the whole of it in one step: claim it, write
        the first version, hand it in."""
        if seat == "CEO" or seat in self.roster.reviewers or seen.done:
            return []
        for task in seen.board.get("claimable", []):
            return [
                ("agent_claim_task", {"task_id": task["id"]}),
                (
                    "write_file",
                    {"path": f"first-version-{task['id']}.txt", "content": FIRST_VERSION},
                ),
                (
                    "agent_complete_task",
                    {"task_id": task["id"], "evidence": "The first version is written."},
                ),
            ]
        return []

    def _next(self, seat: str, seen: Seen) -> Action | None:
        if seat == "CEO":
            return self._ceo(seen)
        if seat in self.roster.reviewers:
            return self._reviewer(seen)
        return self._worker(seat, seen)

    # --- the CEO ---------------------------------------------------------------------

    def _ceo(self, seen: Seen) -> Action | None:
        did = {name for name, _ in seen.done}
        if self.roster.type == "explore":
            return self._ceo_explore(seen, did)
        requirements: list[dict[str, Any]] = seen.plan.get("requirements", [])
        if not requirements and "agent_propose_requirement" not in did:
            return (
                "agent_propose_requirement",
                {
                    "text": "A first usable version of what the goal asks for exists.",
                    "test_kind": "observable",
                    "success_test": "A reader can open the first version and use it.",
                    "estimate_runs": max(1, len(self.roster.worker_teams)),
                    "recurring": self.roster.type == "operate",
                },
            )
        for requirement in requirements:
            if requirement["state"] == "proposed" and self.roster.ceo_accepts:
                return ("agent_accept_requirement", {"requirement_id": requirement["id"]})
        for requirement in requirements:
            if requirement["state"] in ("accepted", "in progress") and requirement.get("ready"):
                task = self._task_for(seen, {"requirement_id": requirement["id"]})
                if task is not None:
                    return task
        return self._own_work(seen)

    def _ceo_explore(self, seen: Seen, did: set[str]) -> Action | None:
        bets: list[dict[str, Any]] = seen.plan.get("bets", [])
        if not bets and "agent_open_bet" not in did:
            return (
                "agent_open_bet",
                {
                    "statement": "The first thing the goal assumes turns out to be true.",
                    "kill_condition": "No evidence for it is found within the window.",
                },
            )
        open_for = {task.get("bet_id") for task in self._all_tasks(seen)}
        for bet in bets:
            if bet["state"] != "active":
                continue
            task = self._task_for(seen, {"bet_id": bet["id"]})
            if task is not None:
                return task
            if bet["id"] not in open_for and bet["id"] not in self.found:
                self.found.add(bet["id"])
                return (
                    "agent_publish_finding",
                    {
                        "bet_id": bet["id"],
                        "result": "inconclusive",
                        "text": "The rehearsal looked and found nothing either way.",
                    },
                )
        return self._own_work(seen)

    def _task_for(self, seen: Seen, serves: dict[str, Any]) -> Action | None:
        """One task for the next team that has none; with no team, one for the CEO."""
        ((kind, served),) = serves.items()
        task: dict[str, Any] = {
            "title": "Build the first version",
            "goal": "Produce the first usable version and say where it is.",
            "success_test": "The first version exists and a reader can use it.",
            "test_kind": "observable",
            "audience": "chairman",
            **serves,
        }
        for team in self.roster.worker_teams or [""]:
            if (kind, served, team) not in self.tasked:
                self.tasked.add((kind, served, team))
                return ("agent_create_task", {**task, "team": team} if team else task)
        return None

    def _own_work(self, seen: Seen) -> Action | None:
        return self._worker("CEO", seen) if not self.roster.worker_teams else None

    # --- everyone else ---------------------------------------------------------------

    def _all_tasks(self, seen: Seen) -> list[dict[str, Any]]:
        found: dict[int, dict[str, Any]] = {}
        for group in ("yours", "claimable", "open"):
            for task in seen.board.get(group, []):
                found[task["id"]] = task
        return list(found.values())

    def _worker(self, seat: str, seen: Seen) -> Action | None:
        did = [name for name, _ in seen.done]
        for task in seen.board.get("yours", []):
            if (
                task["state"] in ("claimed", "doing", "in progress")
                and task.get("claimant") == seat
            ):
                if "write_file" not in did and seat != "CEO":
                    return (
                        "write_file",
                        {
                            "path": f"first-version-{task['id']}.txt",
                            "content": "A first version.\n",
                        },
                    )
                if "agent_complete_task" not in did:
                    return (
                        "agent_complete_task",
                        {
                            "task_id": task["id"],
                            "evidence": "The first version is written and can be opened.",
                        },
                    )
        if "agent_claim_task" not in did:
            for task in seen.board.get("claimable", []):
                return ("agent_claim_task", {"task_id": task["id"]})
        return None

    def _reviewer(self, seen: Seen) -> Action | None:
        did = seen.done
        for task in seen.board.get("yours", []):
            if task["state"] == "review" and ("agent_review_task", task["id"]) not in [
                (name, arguments.get("task_id")) for name, arguments in did
            ]:
                return (
                    "agent_review_task",
                    {
                        "task_id": task["id"],
                        "ok": True,
                        "notes": "The first version is there and can be used.",
                    },
                )
        for requirement in seen.plan.get("requirements", []):
            ruled = [a.get("requirement_id") for n, a in did if n == "agent_rule_requirement"]
            if requirement["state"] in AWAITS_VERDICT and requirement["id"] not in ruled:
                return (
                    "agent_rule_requirement",
                    {"requirement_id": requirement["id"], "passed": True},
                )
        if seen.plan.get("gap_review") in GAP_REVIEW_ASKED and "agent_file_gap_review" not in [
            name for name, _ in did
        ]:
            return ("agent_file_gap_review", {"gaps": []})
        return None


FIRST_VERSION = "A first version.\n"
AWAITS_VERDICT = frozenset({"checking"})
GAP_REVIEW_ASKED = frozenset({"waiting for the reviewer"})
