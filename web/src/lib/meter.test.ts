import { describe, expect, it } from "vitest";
import { listeningLine } from "../panels/memory/PinnedTab";
import { t } from "../strings";
import { meter } from "./meter";

describe("size meter", () => {
  it.each([
    [0, 6000, { percent: 0, over: false, overBy: 0 }],
    [23, 6000, { percent: 0, over: false, overBy: 0 }],
    [3000, 6000, { percent: 50, over: false, overBy: 0 }],
    [6000, 6000, { percent: 100, over: false, overBy: 0 }],
    [6200, 6000, { percent: 100, over: true, overBy: 200 }],
    [5, 0, { percent: 100, over: true, overBy: 5 }],
    [0, 0, { percent: 0, over: false, overBy: 0 }],
  ])("%i of %i", (used, cap, expected) => {
    expect(meter(used, cap)).toEqual(expected);
  });

  it("says the size in words, and says when it is over", () => {
    expect(t.memory.pinned.meter("Project", "23", "6,000")).toBe("Project: 23 of 6,000 tokens");
    expect(t.memory.pinned.over("Agent", "200")).toContain("over its size by 200 tokens");
  });
});

describe("listening score line", () => {
  it("says there are no replies yet while the score is unknown", () => {
    expect(listeningLine({ replies: 0, corrections: 0, listening_score: null })).toBe("no replies yet");
    expect(listeningLine({})).toBe("no replies yet");
  });

  it("gives corrections, replies and the score", () => {
    expect(listeningLine({ replies: 4, corrections: 1, listening_score: 25 })).toBe("1 correction in 4 replies (score 25)");
    expect(listeningLine({ replies: 1, corrections: 2, listening_score: 200 })).toBe("2 corrections in 1 reply (score 200)");
  });
});
