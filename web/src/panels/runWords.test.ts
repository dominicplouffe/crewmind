import { describe, expect, it } from "vitest";
import { aboutWords, reasonWords, runSentence, runStateWords } from "./runWords";

const NOW = Date.parse("2026-11-22T12:00:00Z");

describe("runs in plain words (P18)", () => {
  it("turns the server's reasons into words, and keeps unknown ones as given", () => {
    expect(reasonWords("notice: directive issued")).toBe("a directive");
    expect(reasonWords("message 12 from a person")).toBe("your message");
    expect(reasonWords("heartbeat")).toBe("its regular check-in");
    expect(reasonWords("notice: something new")).toBe("something new");
    expect(reasonWords("task 4")).toBe("task 4");
  });

  it("joins several reasons and drops repeats", () => {
    expect(aboutWords(["message 1 from a person", "message 2 from a person"])).toBe("your message");
    expect(aboutWords(["unread messages", "notice: slow start", "heartbeat"])).toBe(
      "new messages, a slow start and its regular check-in",
    );
    expect(aboutWords([])).toBe("");
  });

  it("says who did what", () => {
    expect(runSentence({ seat: "CEO", kind: "work", reasons: ["notice: directive issued"] })).toBe("CEO worked on a directive");
    expect(runSentence({ seat: "CEO", kind: "chat", reasons: ["message 3 from a person"] })).toBe("CEO replied to your message");
    expect(runSentence({ seat: "Reviewer", kind: "check", reasons: [] })).toBe("Reviewer checked the work");
    expect(runSentence({ seat: "CEO", kind: "dream", reasons: [] })).toBe("CEO ran (dream)");
  });

  it("says where the run is, and when", () => {
    const base = { seat: "CEO", kind: "work", reasons: [], queued_at: "2026-11-22T11:50:00Z" };
    expect(runStateWords({ ...base, state: "finished", ended_at: "2026-11-22T11:56:00Z" }, NOW)).toBe("finished 4 minutes ago");
    expect(runStateWords({ ...base, state: "running" }, NOW)).toBe("working now");
    expect(runStateWords({ ...base, state: "queued" }, NOW)).toBe("waiting to start");
  });
});
