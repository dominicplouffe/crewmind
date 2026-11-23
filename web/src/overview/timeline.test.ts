/** CHAT-19, P18: the project's story from the feed: named, grouped, internals left out. */
import { describe, expect, it } from "vitest";
import type { Schemas } from "../api/client";
import { plainText } from "./now";
import { storyOf, type StorySources } from "./timeline";

const NOW = Date.parse("2026-11-22T15:00:00");
const ME = "person-me";
const MAYA = "seat-maya";
const PRIYA = "seat-priya";
const CEO = "seat-ceo";
const REVIEWER = "seat-reviewer";

let next = 0;
/** A feed line `minutes` before now. */
function line(minutes: number, type: string, text: string, actor: string): Schemas["FeedItem"] {
  next += 1;
  return { id: next, at: new Date(NOW - minutes * 60_000).toISOString(), type, text, actor };
}

function sources(feed: Schemas["FeedItem"][]): StorySources {
  return {
    feed,
    me: ME,
    tasks: [
      { id: 1, title: "Write the landing-page copy", claimant: "Maya" },
      { id: 2, title: "Write the FAQ", claimant: "Maya" },
      { id: 4, title: "Pick the email provider", claimant: "Priya" },
      { id: 5, title: "Wire the sign-up form", claimant: null },
    ],
    requirements: [
      { id: 1, text: "The landing page explains Fieldnotes." },
      { id: 2, text: "The pricing table lists three plans." },
      { id: 3, text: "The sign-up form works." },
    ],
    items: [
      { id: 4, kind: "proposed scope", title: "Proposed scope: requirement 4", outcome: null, fields: {} },
      { id: 6, kind: "approval: spend", title: "Spend 15.00 USD", outcome: null, fields: {} },
      { id: 7, kind: "question", title: "Question about other", outcome: null, fields: { question: "Show a yearly price?" } },
      { id: 9, kind: "question", title: "Question about tone", outcome: "Plain", fields: { question: "Which tone?" } },
    ],
    files: [
      { name: "landing-copy.md", kind: "deliverable" },
      { name: "providers.csv", kind: "deliverable" },
      { name: "signup.ts", kind: "deliverable" },
      { name: "notes.txt", kind: "working" },
    ],
  };
}

function texts(source: StorySources): string[] {
  return storyOf(source, 20, NOW).flatMap((day) => day.entries.map((entry) => plainText(entry.parts)));
}

describe("storyOf", () => {
  it.each<[string, Schemas["FeedItem"][], string[]]>([
    ["a task done names its title and who did it", [line(5, "task.state_changed", "Task 1 is now done.", REVIEWER)], ["Maya finished Write the landing-page copy"]],
    ["a file delivered names the file and its author", [line(5, "artifact.version_added", "Maya saved version 1 of landing-copy.md.", MAYA)], ["Maya delivered landing-copy.md"]],
    ["a new version reads as an update", [line(5, "artifact.version_added", "Maya saved version 3 of landing-copy.md.", MAYA)], ["Maya updated landing-copy.md"]],
    ["a working file is left out", [line(5, "artifact.version_added", "Maya saved version 1 of notes.txt.", MAYA)], []],
    ["a requirement accepted by the chairman reads You", [line(5, "requirement.state_changed", "Requirement 2 is now accepted.", ME)], ["You accepted The pricing table lists three plans."]],
    ["a requirement met", [line(5, "requirement.state_changed", "Requirement 1 is now met.", "platform")], ["Requirement met: The landing page explains Fieldnotes."]],
    ["a team hired", [line(5, "team.hired", "Team web was hired (1 x Software Engineer).", ME)], ["You hired the web team"]],
    ["a question asked uses the question", [line(5, "item.state_changed", "Item 7 is now open.", "someone")], ["A question for you: Show a yearly price?"]],
    ["an approval asked", [line(5, "item.state_changed", "Item 6 is now open.", "someone")], ["Waiting for your approval: Spend 15.00 USD"]],
    ["a decision made", [line(5, "item.state_changed", "Item 9 is now decided.", ME)], ["You decided Which tone? (Plain)"]],
    ["a proposed-scope item is told by its requirement instead", [line(5, "item.state_changed", "Item 4 is now open.", CEO)], []],
    ["the project starting", [line(5, "project.created", "The project was created.", ME), line(5, "project.state_changed", "The project went from draft to running.", ME)], ["You started the project"]],
    ["a hold, as the server says it", [line(5, "project.hold_added", "A hold was added: chairman. It lifts by /resume.", ME)], ["A hold was added: chairman. It lifts by /resume."]],
    ["a budget threshold", [line(5, "budget.threshold_reached", "The budget passed its warn level.", "platform")], ["The budget passed its warn level."]],
  ])("%s", (_name, feed, expected) => {
    expect(texts(sources(feed))).toEqual(expected);
  });

  it.each([
    ["run.state_changed", "A work run is now queued."],
    ["chat_session.state_changed", "Chat session 1 is now warm."],
    ["directive.state_changed", "Directive 3 is now issued."],
    ["setting.changed", "budget.tokens changed from 1 to 2."],
    ["member.added", "Person 123: added."],
    ["seat.created", "Maya joined the crew."],
    ["task.state_changed", "Task 2 is now claimed."],
    ["task.state_changed", "Task 99 is now done."],
    ["requirement.state_changed", "Requirement 1 is now in progress."],
    ["item.state_changed", "Item 77 is now open."],
  ])("CHAT-19 leaves out %s (%s)", (type, text) => {
    expect(texts(sources([line(5, type, text, ME)]))).toEqual([]);
  });

  it("groups neighbours of one kind by one actor and lists them oldest first", () => {
    const feed = [
      line(30, "task.state_changed", "Task 2 is now claimed.", MAYA),
      line(20, "artifact.version_added", "Priya saved version 1 of providers.csv.", PRIYA),
      line(19, "artifact.version_added", "Priya saved version 1 of signup.ts.", PRIYA),
      line(12, "requirement.state_changed", "Requirement 1 is now proposed.", CEO),
      line(12, "requirement.state_changed", "Requirement 2 is now proposed.", CEO),
      line(12, "requirement.state_changed", "Requirement 3 is now proposed.", CEO),
      line(11, "artifact.version_added", "CEO saved version 1 of landing-copy.md.", CEO),
      line(2, "task.state_changed", "Task 5 is now blocked.", PRIYA),
    ];
    const days = storyOf(sources(feed), 20, NOW);
    expect(days).toHaveLength(1);
    expect(days[0]?.label).toBe("Today");
    const entries = days[0]?.entries ?? [];
    expect(entries.map((entry) => plainText(entry.parts))).toEqual([
      "Priya is blocked on Wire the sign-up form",
      "CEO delivered landing-copy.md",
      "CEO proposed 3 requirements",
      "Priya delivered 2 files",
    ]);
    expect(entries[2]?.details).toEqual([
      "The landing page explains Fieldnotes.",
      "The pricing table lists three plans.",
      "The sign-up form works.",
    ]);
    expect(entries[3]?.details).toEqual(["providers.csv", "signup.ts"]);
    expect(entries[0]?.who).toEqual({ name: "Priya", kind: "agent" });
    expect(entries[0]?.when).toBe("2 minutes ago");
  });

  it("splits days and keeps to the limit", () => {
    const feed = [
      line(26 * 60, "task.state_changed", "Task 4 is now done.", REVIEWER),
      line(60, "task.state_changed", "Task 1 is now done.", REVIEWER),
      line(1, "requirement.state_changed", "Requirement 3 is now met.", "platform"),
    ];
    const days = storyOf(sources(feed), 20, NOW);
    expect(days.map((day) => day.label)).toEqual(["Today", "Yesterday"]);
    expect(storyOf(sources(feed), 1, NOW).flatMap((day) => day.entries)).toHaveLength(1);
  });
});
