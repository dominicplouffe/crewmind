import { describe, expect, it } from "vitest";
import {
  answerFor,
  credentialsInHint,
  decisionName,
  documentProblem,
  draftSummary,
  elementName,
  gradeOf,
  quickSteps,
  readinessReasons,
  sourceTag,
  specFileName,
  stageOf,
  visibleLines,
  type Drafting,
  type Line,
  type Question,
} from "./logic";

function question(extra: Partial<Question> = {}): Question {
  return {
    id: 4,
    settles: "finish_line",
    text: "What record shows it is finished?",
    options: ["The signed proof", "A draft", "Something else"],
    recommended: 0,
    changes: "It changes the finish line.",
    ...extra,
  };
}

function view(extra: Partial<Drafting> = {}): Drafting {
  return {
    drafting_id: "d1",
    state: "drafting",
    quick: false,
    waiting_for: "you",
    failure: null,
    lines: [],
    questions: [],
    ledger: [],
    draft: null,
    grade: null,
    rehearsal: null,
    ready: false,
    not_ready_because: [],
    rules_hit: [],
    project_id: null,
    ...extra,
  };
}

const line = (id: number, author: string, detail: Line["detail"] = null): Line => ({
  id,
  author,
  body: `line ${id}`,
  detail,
  at: "2030-01-07T09:00:00Z",
});

describe("answerFor (FND-3)", () => {
  it("sends empty text to accept the recommendation", () => {
    expect(answerFor(question(), { kind: "recommended" })).toBe("");
  });

  it("sends nothing when the question recommends nothing, so who pays is never chosen for the person", () => {
    const whoPays = question({ settles: "who_pays", recommended: null });
    expect(answerFor(whoPays, { kind: "recommended" })).toBeNull();
    expect(answerFor(whoPays, { kind: "own", text: "  " })).toBeNull();
    expect(answerFor(whoPays, { kind: "own", text: "yes" })).toBeNull();
  });

  it("sends the option's letter", () => {
    expect(answerFor(question(), { kind: "option", index: 0 })).toBe("a");
    expect(answerFor(question(), { kind: "option", index: 2 })).toBe("c");
  });

  it("sends nothing for an option the question does not have", () => {
    expect(answerFor(question(), { kind: "option", index: 3 })).toBeNull();
    expect(answerFor(question(), { kind: "option", index: -1 })).toBeNull();
  });

  it("sends the person's own words, trimmed", () => {
    expect(answerFor(question(), { kind: "own", text: "  The printer's receipt. " })).toBe("The printer's receipt.");
  });

  it("treats an empty box, or a plain yes, as accepting the recommendation", () => {
    expect(answerFor(question(), { kind: "own", text: "" })).toBe("");
    expect(answerFor(question(), { kind: "own", text: "Yes" })).toBe("");
  });
});

describe("ledger and grade names (FND-5, FND-7)", () => {
  it("tags each source in plain words and shows an unknown one as given", () => {
    expect(sourceTag("words")).toBe("your words");
    expect(sourceTag("answer")).toBe("your answer");
    expect(sourceTag("assumption")).toBe("assumed");
    expect(sourceTag("imported")).toBe("imported");
  });

  it("names a decision, a passage of the document, and anything else", () => {
    expect(decisionName("who_pays")).toBe("Who pays");
    expect(decisionName("item:12")).toBe("Passage 12 of your document");
    expect(decisionName("some_new_thing")).toBe("some new thing");
  });

  it("names a goal element", () => {
    expect(elementName("quality_bar")).toBe("Quality bar");
    expect(elementName("new_element")).toBe("new element");
  });
});

describe("visibleLines", () => {
  it("leaves out the line of a question that is shown as an open card", () => {
    const lines = [
      line(1, "person"),
      line(2, "founder", { kind: "question", id: 4 }),
      line(3, "founder"),
      line(5, "founder", { kind: "question", id: 9 }),
    ];
    expect(visibleLines(lines, [question({ id: 9 })]).map((item) => item.id)).toEqual([1, 2, 3]);
    expect(visibleLines(lines, []).map((item) => item.id)).toEqual([1, 2, 3, 5]);
  });
});

describe("stageOf", () => {
  it.each([
    [view(), "you"],
    [view({ waiting_for: "the Founder" }), "founder"],
    [view({ ready: true }), "ready"],
    [view({ quick: true, waiting_for: "the Founder" }), "quick"],
    [view({ quick: true, state: "creating", waiting_for: "nobody" }), "quick"],
    [view({ state: "created", project_id: "p1", waiting_for: "nobody" }), "done"],
    [view({ quick: true, state: "started", project_id: "p1", waiting_for: "nobody" }), "done"],
    [view({ quick: true, state: "failed", waiting_for: "nobody" }), "failed"],
  ] as const)("%#", (drafting, stage) => {
    expect(stageOf(drafting)).toBe(stage);
  });
});

describe("readinessReasons (FND-5)", () => {
  it("says how many questions wait in plain words", () => {
    expect(readinessReasons(["1 question(s) are waiting for an answer."])).toEqual([
      { text: "1 question is waiting for your answer.", parts: [] },
    ]);
    expect(readinessReasons(["3 question(s) are waiting for an answer."])[0]?.text).toBe(
      "3 questions are waiting for your answer.",
    );
  });

  it("lays a reason that lists several things out as a list", () => {
    expect(readinessReasons(["Not yet decided: The budget; The team; The quality setting."])).toEqual([
      { text: "Not yet decided:", parts: ["The budget", "The team", "The quality setting"] },
    ]);
  });

  it("shows every other reason as the server gave it", () => {
    const reasons = [
      "This draft has not been rehearsed.",
      "The rehearsal did not reach a first close: Stalls before work is claimed.",
      "Not yet decided: The budget.",
    ];
    expect(readinessReasons(reasons)).toEqual(reasons.map((text) => ({ text, parts: [] })));
  });
});

describe("quickSteps (FND-12)", () => {
  const statuses = (state: string): string[] => quickSteps(state).map((step) => step.status);

  it("marks the step in progress and the ones before it done", () => {
    expect(statuses("drafting")).toEqual(["now", "todo", "todo", "todo"]);
    expect(statuses("starting")).toEqual(["done", "done", "now", "todo"]);
  });

  it("marks everything done once started", () => {
    expect(statuses("started")).toEqual(["done", "done", "done", "done"]);
  });

  it("marks nothing done when it failed, because nothing was created", () => {
    expect(statuses("failed")).toEqual(["todo", "todo", "todo", "todo"]);
  });
});

describe("credentialsInHint", () => {
  it("reads the names the server lists", () => {
    expect(credentialsInHint("Name one: main, spare.")).toEqual(["main", "spare"]);
  });

  it("finds none when there is no list", () => {
    expect(credentialsInHint(null)).toEqual([]);
    expect(credentialsInHint("Choose a credential")).toEqual([]);
  });
});

describe("draftSummary and gradeOf", () => {
  it("picks out what the side panel shows", () => {
    const summary = draftSummary({
      name: "Bird guide",
      type: "deliver",
      goal: "Publish a guide.",
      quality: "best",
      budget_tokens: 5000,
      paying_credential: null,
      deadline: null,
      teams: [{ name: "Entries", role: "researcher", members: ["Rey", "Sol"], version: null }],
      settings: { "run.concurrency": 2 },
    });
    expect(summary).toEqual({
      name: "Bird guide",
      type: "deliver",
      goal: "Publish a guide.",
      quality: "best",
      budgetTokens: 5000,
      deadline: null,
      payingCredential: null,
      teams: [{ name: "Entries", role: "researcher", members: ["Rey", "Sol"] }],
      settings: [["run.concurrency", 2]],
    });
  });

  it("is empty when there is no draft, and survives a draft with parts missing", () => {
    expect(draftSummary(null)).toBeNull();
    expect(draftSummary({ name: "Only a name" })).toMatchObject({ name: "Only a name", teams: [], settings: [] });
  });

  it("reads a grade, and treats an unknown grade word as missing", () => {
    expect(gradeOf(null)).toBeNull();
    expect(gradeOf({ summary: "No elements" })).toBeNull();
    const grade = gradeOf({
      ready: false,
      summary: "Not ready.",
      missing: ["standard"],
      weak: [],
      elements: [
        { element: "finish_line", grade: "present", quote: "THE FINISH LINE", reason: "", fix: "" },
        { element: "standard", grade: "absent", fix: "Name a reference class." },
      ],
    });
    expect(grade?.ready).toBe(false);
    expect(grade?.elements.map((element) => element.grade)).toEqual(["present", "missing"]);
    expect(grade?.elements[1]).toMatchObject({ quote: "", fix: "Name a reference class." });
  });
});

describe("documentProblem and specFileName", () => {
  it("takes a text file and refuses anything else, an empty file, or one too long", () => {
    expect(documentProblem("brief.md", "Some text")).toBeNull();
    expect(documentProblem("BRIEF.TXT", "Some text")).toBeNull();
    expect(documentProblem("brief.pdf", "Some text")).toContain("not a text file");
    expect(documentProblem("brief.txt", "  \n")).toContain("empty");
    expect(documentProblem("brief.txt", "x".repeat(200_001))).toContain("too long");
  });

  it("names the exported file after the project", () => {
    expect(specFileName("Hollin Valley: bird guide!")).toBe("hollin-valley-bird-guide.spec.json");
    expect(specFileName("???")).toBe("project.spec.json");
  });
});
