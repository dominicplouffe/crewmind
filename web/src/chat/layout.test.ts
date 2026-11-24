import { describe, expect, it } from "vitest";
import type { Message } from "../api/client";
import { dayLabel, placements } from "./layout";

const WORDS = { today: "Today", yesterday: "Yesterday" };
const NOW = new Date("2026-11-24T15:00:00");

let next = 1;
function message(extra: Partial<Message>): Message {
  return {
    id: next++, channel: "project chat", author_kind: "person", author: "Ada", kind: "message", body: "Hello",
    reply_to: null, thread_id: null, run_id: null, detail: null, at: "2026-11-24T10:00:00", ...extra,
  };
}

describe("placements: day dividers, groups and reply quotes (CHAT-10, CHAT-11)", () => {
  it("names the day above the first message of each day", () => {
    const shown = placements(
      [message({ at: "2026-11-23T09:00:00" }), message({ at: "2026-11-23T09:05:00" }), message({ at: "2026-11-24T08:00:00" })],
      NOW,
      WORDS,
    );
    expect(shown.map((entry) => entry.day)).toEqual(["Yesterday", null, "Today"]);
  });

  it("groups a speaker's messages in a row, and starts a new group for anyone else or a new day", () => {
    const shown = placements(
      [
        message({ author: "Ada" }),
        message({ author: "Ada" }),
        message({ author_kind: "agent", author: "CEO" }),
        message({ author_kind: "agent", author: "CEO" }),
        message({ author_kind: "agent", author: "CEO", at: "2026-11-25T08:00:00" }),
      ],
      NOW,
      WORDS,
    );
    expect(shown.map((entry) => entry.continued)).toEqual([false, true, false, true, false]);
  });

  it("never groups nightsquad's own lines or action cards, nor what follows them", () => {
    const shown = placements(
      [
        message({ author_kind: "agent", author: "CEO" }),
        message({ author_kind: "platform", author: "nightsquad", kind: "status" }),
        message({ author_kind: "agent", author: "CEO" }),
        message({ author_kind: "agent", author: "CEO", detail: { kind: "action card", card: 3 } }),
      ],
      NOW,
      WORDS,
    );
    expect(shown.map((entry) => entry.continued)).toEqual([false, false, false, false]);
  });

  it("groups lines said while drafting by who said them", () => {
    const drafted = (author: string): Message =>
      message({ author_kind: "platform", author: "nightsquad", kind: "status", detail: { kind: "drafting", author } });
    const shown = placements([drafted("founder"), drafted("founder"), drafted("person")], NOW, WORDS);
    expect(shown.map((entry) => entry.continued)).toEqual([false, true, false]);
  });

  it("quotes the message a reply answers only when it is not the one just above", () => {
    const question = message({ body: "Are you there?" });
    const other = message({ body: "And another thing" });
    const answer = message({ author_kind: "agent", author: "CEO", reply_to: question.id });
    const adjacent = message({ author_kind: "agent", author: "CEO", reply_to: answer.id });
    const shown = placements([question, other, answer, adjacent], NOW, WORDS);
    expect(shown.map((entry) => entry.quote)).toEqual([false, false, true, false]);
  });

  it("starts a new group for a reply to something further up, so its quote has a head to sit under", () => {
    const question = message({ body: "First" });
    const first = message({ author_kind: "agent", author: "CEO" });
    const late = message({ author_kind: "agent", author: "CEO", reply_to: question.id });
    expect(placements([question, first, late], NOW, WORDS).map((entry) => entry.continued)).toEqual([false, false, false]);
  });
});

describe("dayLabel", () => {
  it("gives the date, with the year only when it is not this year", () => {
    expect(dayLabel("2026-03-02T10:00:00", NOW, WORDS)).toContain("March");
    expect(dayLabel("2026-03-02T10:00:00", NOW, WORDS)).not.toContain("2026");
    expect(dayLabel("2025-03-02T10:00:00", NOW, WORDS)).toContain("2025");
  });
});
