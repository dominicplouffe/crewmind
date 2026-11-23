"""Drafting in the terminal (IF-4.6, IF-4.7): the session's choices, with the server
played by a list of views."""

from __future__ import annotations

from typing import Any

from crewmind.surfaces.cli.draft import Session, prompt_for, question_text

QUESTION: dict[str, Any] = {
    "id": 7,
    "settles": "finish_line",
    "text": "Is the signed proof the finish line?",
    "options": ["Yes, the signed proof", "No, the printed copies"],
    "recommended": 0,
    "changes": "What counts as finished.",
}
PAYER = {
    **QUESTION,
    "id": 8,
    "settles": "who_pays",
    "options": ["main", "spare"],
    "recommended": None,
}

NO_MAIN = "You have no credential named main. Add it."
SECRET = "sk-typed-in-secret"


def view(**changes: Any) -> dict[str, Any]:
    return {
        "state": "drafting", "waiting_for": "you", "lines": [], "questions": [], "ledger": [],
        "ready": False, "not_ready_because": [], "failure": None, "project_id": None, **changes,
    }  # fmt: skip


class Server:
    """Answers `founder.show` from a list of views, and records every other call."""

    def __init__(self, *views: dict[str, Any], results: dict[str, Any] | None = None) -> None:
        self.views, self.results = list(views), results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, operation: str, /, **values: Any) -> dict[str, Any]:
        if operation == "founder.show":
            return self.views.pop(0) if len(self.views) > 1 else self.views[0]
        self.calls.append((operation, values))
        return self.results.get(operation, {})


def session(
    server: Server, *typed: str, secrets: tuple[str, ...] = ()
) -> tuple[Session, list[str]]:
    answers, hidden = list(typed), list(secrets)
    printed: list[str] = []
    made = Session(
        server,  # pyright: ignore[reportArgumentType]
        ask=lambda _: answers.pop(0),
        secret=lambda _: hidden.pop(0),
        say=printed.append,
        sleep=lambda _: None,
    )
    return made, printed


def test_IF_4_6_a_question_shows_its_recommendation_and_who_pays_shows_none() -> None:
    """IF-4.6, FND-3: each question arrives with its recommended answer marked; who pays
    is never pre-selected, so nothing is marked and Enter is not offered."""
    assert "a. Yes, the signed proof  (recommended)" in question_text(QUESTION)
    assert "It changes: What counts as finished." in question_text(QUESTION)
    assert "Enter = recommended" in prompt_for(QUESTION)
    assert "(recommended)" not in question_text(PAYER)
    assert "Enter" not in prompt_for(PAYER)


def test_IF_4_6_enter_a_letter_and_free_text_are_sent_as_typed_and_the_talk_resumes() -> None:
    """IF-4.6, FND-1: Enter, a letter and the person's own words are each sent as the
    answer; `/rest` accepts the remaining recommendations; `/quit` leaves and says how to
    resume, because the conversation lives on the server. While the Founder is thinking
    the terminal waits."""
    thinking = view(waiting_for="the Founder")
    asking = view(questions=[QUESTION])
    server = Server(thinking, asking, asking, asking, asking, asking)
    made, printed = session(server, "", "b", "Neither: the bound copies.", "/rest", "/quit")
    assert made.run("d1") is None
    assert server.calls == [
        ("founder.answer", {"drafting_id": "d1", "question_id": 7, "answer": ""}),
        ("founder.answer", {"drafting_id": "d1", "question_id": 7, "answer": "b"}),
        (
            "founder.answer",
            {"drafting_id": "d1", "question_id": 7, "answer": "Neither: the bound copies."},
        ),
        ("founder.accept_rest", {"drafting_id": "d1"}),
    ]
    assert printed[-1] == "\nKept. Resume with: crewmind draft --resume d1"


WORDPRESS = "The secret wordpress, for blog-writer is missing."


def test_IF_4_7_after_creation_missing_credentials_are_asked_for_and_start_is_offered() -> None:
    """IF-4.7, FND-13, IF-4.5: once the ledger is confirmed and the project created, each
    missing credential is asked for with hidden input and may be skipped; what is still
    missing is listed; who in the crew would wait is listed, and starting then means starting
    without it (CON-5)."""
    ledger = [{"settles": "finish_line", "value": "The signed proof", "source": "answer"}]
    created = {
        "project_id": "p1", "name": "Bird guide", "state": "draft", "can_start": False,
        "missing": [NO_MAIN, "The spec asks for email, which is not available in this version."],
        "missing_credentials": ["main"],
    }  # fmt: skip
    server = Server(
        view(ready=True, ledger=ledger),
        results={"founder.create": created, "projects.start": {"state": "running"}},
    )
    made, printed = session(server, "y", "anthropic", "y", secrets=(SECRET,))
    result = made.run("d1")
    assert result == created
    assert "  finish_line: The signed proof (answer)" in printed
    assert result is not None
    made.after_creation(result)
    assert [name for name, _ in server.calls] == [
        "founder.create", "credentials.add", "models.set_payer", "projects.start",
    ]  # fmt: skip
    assert server.calls[1][1] == {
        "name": "main",
        "provider": "anthropic",
        "key": "sk-typed-in-secret",
    }
    assert not any("sk-typed-in-secret" in line for line in printed)
    assert any("email" in line for line in printed)
    assert printed[-1] == "Started. The project is running."

    # CON-5: who would wait is listed, and starting means starting without it, said so.
    waiting = {**created, "missing": [], "missing_credentials": [], "waiting": [WORDPRESS]}
    server = Server(view(), results={"projects.start": {"state": "running"}})
    made, printed = session(server, "")
    made.after_creation(waiting)
    assert server.calls == []
    assert any(WORDPRESS in line for line in printed)
    assert printed[-1] == "\nStart it with `crewmind projects start` when you are ready."
    made, printed = session(server, "y")
    made.after_creation(waiting)
    assert server.calls == [("projects.start", {"project_id": "p1", "without_missing": True})]
