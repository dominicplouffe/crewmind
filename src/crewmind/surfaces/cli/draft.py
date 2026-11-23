"""`crewmind draft`: drafting a project with the Founder in the terminal (IF-4.6, IF-4.7).

A client of the `founder.*` operations. It defines no operation and holds no rule: the
conversation lives on the server, so it can be left here and resumed anywhere."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import typer

API = "/v1"
POLL_SECONDS = 1.0
REST, QUIT = "/rest", "/quit"
HELP = f"Enter accepts the recommendation. A letter picks an option. Or answer in your own \
words. {REST} uses the Founder's recommendations for everything still open. {QUIT} leaves; \
the conversation is kept."


class Refused(Exception):
    def __init__(self, envelope: dict[str, Any]) -> None:
        super().__init__(envelope.get("message", "Refused."))
        self.envelope = envelope


class Founder:
    """The few calls the terminal needs, over HTTP as the signed-in person."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def call(self, operation: str, /, **values: Any) -> dict[str, Any]:
        path = f"{API}/{operation.replace('.', '/')}"
        read = operation in ("founder.show", "founder.list", "credentials.list")
        response = (
            self._client.get(path, params=values) if read else self._client.post(path, json=values)
        )
        body: dict[str, Any] = response.json()
        if response.status_code != 200:
            raise Refused(body)
        return body


def question_text(question: dict[str, Any]) -> str:
    """One question as the terminal shows it (IF-4.6): the options lettered, the
    recommended one marked, and what the answer changes. Nothing is marked when nothing
    is recommended, as for who pays."""
    lines = [question["text"]]
    for index, option in enumerate(question["options"]):
        mark = "  (recommended)" if index == question["recommended"] else ""
        lines.append(f"  {chr(ord('a') + index)}. {option}{mark}")
    lines.append(f"  It changes: {question['changes']}")
    return "\n".join(lines)


def prompt_for(question: dict[str, Any]) -> str:
    return (
        "Your answer [Enter = recommended]"
        if question["recommended"] is not None
        else ("Your answer")
    )


class Session:
    """One sitting at a drafting conversation."""

    def __init__(
        self,
        founder: Founder,
        ask: Callable[[str], str],
        secret: Callable[[str], str],
        say: Callable[[str], None],
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.founder, self.ask, self.secret, self.say, self.sleep = founder, ask, secret, say, sleep
        self.shown = 0

    def _print_new(self, view: dict[str, Any]) -> None:
        for line in view["lines"]:
            if line["id"] <= self.shown:
                continue
            self.shown = line["id"]
            detail: dict[str, Any] = line["detail"] or {}
            if line["author"] == "person" or detail.get("kind") == "question":
                continue
            who = "Founder" if line["author"] == "founder" else "crewmind"
            self.say(f"\n{who}: {line['body']}")

    def wait(self, drafting_id: str) -> dict[str, Any]:
        """Until the Founder has spoken. Its turn runs on the server."""
        view = self.founder.call("founder.show", drafting_id=drafting_id)
        while view["waiting_for"] == "the Founder" and view["state"] in (
            "drafting",
            "creating",
            "starting",
        ):
            self.sleep(POLL_SECONDS)
            view = self.founder.call("founder.show", drafting_id=drafting_id)
        self._print_new(view)
        return view

    def run(self, drafting_id: str) -> dict[str, Any] | None:
        """Returns what was created, or None when the person left or nothing was."""
        ref = {"drafting_id": drafting_id}
        while True:
            view = self.wait(drafting_id)
            if view["state"] != "drafting":
                if view["state"] == "failed":
                    self.say(f"\nNothing was created: {view['failure']}")
                    return None
                return {"project_id": view["project_id"], "state": view["state"], "missing": []}
            if view["questions"]:
                question = view["questions"][0]
                self.say("\n" + question_text(question))
                answer = self.ask(prompt_for(question)).strip()
                if answer == QUIT:
                    return self._leave(drafting_id)
                if answer == REST:
                    self.founder.call("founder.accept_rest", **ref)
                    continue
                try:
                    self.founder.call(
                        "founder.answer", **ref, question_id=question["id"], answer=answer
                    )
                except Refused as refused:
                    self.say(str(refused))
                continue
            if view["ready"]:
                self.say("\nThe draft is ready. The ledger:")
                for entry in view["ledger"]:
                    self.say(f"  {entry['settles']}: {entry['value']} ({entry['source']})")
                if self.ask("Create the project? [Y/n]").strip().lower() in ("", "y", "yes"):
                    return self.founder.call("founder.create", **ref)
            elif view["not_ready_because"]:
                self.say("\nNot ready yet: " + " ".join(view["not_ready_because"]))
            said = self.ask("You").strip()
            if said == QUIT:
                return self._leave(drafting_id)
            if said == REST:
                self.founder.call("founder.accept_rest", **ref)
            elif said:
                self.founder.call("founder.say", **ref, body=said)

    def _leave(self, drafting_id: str) -> None:
        self.say(f"\nKept. Resume with: crewmind draft --resume {drafting_id}")

    def after_creation(self, created: dict[str, Any]) -> None:
        """IF-4.7, FND-13: ask for each missing credential, hidden and skippable; print
        what is still missing; offer to start only when nothing blocks it."""
        project = created["project_id"]
        self.say(f"\nCreated: {created.get('name', project)} ({project}).")
        for name in created.get("missing_credentials", []):
            key = self.secret(f"API key for the credential {name} (Enter to skip)")
            if not key:
                continue
            provider = self.ask(f"Which provider is {name} for? (for example anthropic)").strip()
            try:
                self.founder.call("credentials.add", name=name, provider=provider, key=key)
                self.founder.call("models.set_payer", project_id=project, credential=name)
                created["missing"] = [line for line in created["missing"] if name not in line]
                self.say(f"Added {name}. It pays for this project.")
            except Refused as refused:
                self.say(str(refused))
        if created["missing"]:
            self.say("\nStill to set up:")
            for line in created["missing"]:
                self.say(f"  - {line}")
        waiting = list(created.get("waiting", []))
        if waiting:
            self.say("\nSome of the crew could not work yet:")
            for line in waiting:
                self.say(f"  - {line}")
        if created.get("state") != "draft":
            return
        question = (
            "Start now without it? Those agents wait until it is added. [y/N]"
            if waiting
            else "Start the project now? [y/N]"
        )
        if self.ask(question).strip().lower() in ("y", "yes"):
            try:
                started = self.founder.call(
                    "projects.start", project_id=project, without_missing=bool(waiting)
                )
                self.say(f"Started. The project is {started['state']}.")
            except Refused as refused:
                self.say(str(refused))
        else:
            self.say("\nStart it with `crewmind projects start` when you are ready.")


def run_draft(
    client: httpx.Client,
    *,
    brief: str | None,
    document: Path | None,
    resume: str | None,
    quick: bool,
    credential: str | None,
) -> None:
    founder = Founder(client)
    session = Session(
        founder,
        ask=lambda label: typer.prompt(label, default="", show_default=False),
        secret=lambda label: typer.prompt(label, default="", show_default=False, hide_input=True),
        say=typer.echo,
    )
    try:
        if resume:
            drafting_id = resume
        else:
            brief = brief or typer.prompt("What do you want done?")
            if quick:
                started = founder.call("founder.quick", brief=brief, credential=credential)
            else:
                text = document.read_text(encoding="utf-8") if document else None
                started = founder.call("founder.start", brief=brief, document=text)
                typer.echo(HELP)
            drafting_id = started["drafting_id"]
        created = session.run(drafting_id)
        if created and created.get("project_id"):
            session.after_creation(created)
    except Refused as refused:
        typer.echo(str(refused), err=True)
        if refused.envelope.get("hint"):
            typer.echo(refused.envelope["hint"], err=True)
        raise typer.Exit(3) from refused


def run_eval(client: httpx.Client, pairs: list[tuple[Path, Path]]) -> int:
    """FND-7: grade each goal with the install's Founder model and compare with its hand
    grade, element by element. Returns 0 when every verdict and every element agrees."""
    import json

    founder, disagreements = Founder(client), 0
    for goal_file, grades_file in pairs:
        goal = goal_file.read_text(encoding="utf-8")
        hand = json.loads(grades_file.read_text(encoding="utf-8"))
        wanted = {row["element"]: row["grade"] for row in hand["grades"]}
        try:
            got = founder.call("goals.grade", goal=goal)
        except Refused as refused:
            typer.echo(f"{goal_file.name}: the grade was refused: {refused}")
            disagreements += 1
            continue
        graded = {row["element"]: row["grade"] for row in got["elements"]}
        differ = [
            f"{element}: hand {wanted[element]}, model {graded.get(element)}"
            for element in wanted
            if graded.get(element) != wanted[element]
        ]
        verdict = "agrees" if got["ready"] == hand["ready"] else "DISAGREES"
        typer.echo(
            f"{goal_file.name}: ready={got['ready']} (hand: {hand['ready']}, {verdict}); "
            f"{len(wanted) - len(differ)} of {len(wanted)} elements agree."
        )
        for line in differ:
            typer.echo(f"  {line}")
        disagreements += len(differ) + (got["ready"] != hand["ready"])
    return 0 if disagreements == 0 else 1
