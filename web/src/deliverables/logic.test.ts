/** ART-3, CHAT-16: the deliverables gallery groups, filters and sorts files without hiding any rule. */
import { describe, expect, it } from "vitest";
import type { Artifact } from "../api/client";
import { arrange, authorKind, categoryOf, countByFilter, defaultScope, excerptLines, markdownExcerpt } from "./logic";

function file(name: string, extra: Partial<Artifact> = {}): Artifact {
  return {
    name,
    kind: "deliverable",
    media_type: "",
    size: 10,
    status: "draft",
    versions: 1,
    last_author: "CEO",
    last_change: "2026-11-22T10:00:00Z",
    locked: false,
    mark: null,
    audience: "chairman",
    superseded_by: null,
    ...extra,
  };
}

describe("categoryOf", () => {
  it.each([
    ["brief.md", "", "documents"],
    ["notes.txt", "", "documents"],
    ["site/index.html", "text/html", "documents"],
    ["report.pdf", "application/pdf", "documents"],
    ["app.py", "", "code"],
    ["logo.png", "image/png", "images"],
    ["prices.csv", "", "data"],
    ["data.json", "application/json", "data"],
    ["song.mp3", "audio/mpeg", "other"],
    ["archive.zip", "application/zip", "other"],
  ])("%s is %s", (name, mediaType, category) => {
    expect(categoryOf({ name, media_type: mediaType })).toBe(category);
  });
});

describe("arrange", () => {
  const items = [
    file("b.md", { last_change: "2026-11-22T09:00:00Z", status: "delivered" }),
    file("a.py", { last_change: "2026-11-22T11:00:00Z" }),
    file("w.txt", { kind: "working", last_change: "2026-11-22T12:00:00Z" }),
    file("old.md", { superseded_by: "b.md" }),
    file("up.png", { kind: "upload", media_type: "image/png", last_author: "Dom", status: "in review" }),
  ];

  it("keeps working and replaced files out of the delivered scope", () => {
    expect(arrange(items, "all", "recent", "delivered").map((item) => item.name)).toEqual(["a.py", "up.png", "b.md"]);
    expect(arrange(items, "all", "recent", "everything")).toHaveLength(5);
  });

  it("filters by type and sorts by name or status", () => {
    expect(arrange(items, "documents", "name", "everything").map((item) => item.name)).toEqual(["b.md", "old.md", "w.txt"]);
    expect(arrange(items, "all", "status", "delivered").map((item) => item.name)).toEqual(["b.md", "up.png", "a.py"]);
  });

  it("counts each filter, and the parts add up to all", () => {
    const counts = countByFilter(items, "delivered");
    expect(counts).toEqual({ all: 3, documents: 1, code: 1, images: 1, data: 0, other: 0 });
  });

  it("starts in everything when nothing is delivered yet", () => {
    expect(defaultScope(items)).toBe("delivered");
    expect(defaultScope([file("w.txt", { kind: "working" })])).toBe("everything");
  });
});

describe("authorKind", () => {
  const seats = new Set(["CEO"]);
  it.each([
    [file("a", { last_author: "CEO" }), "agent"],
    [file("a", { kind: "upload", last_author: "Dom" }), "person"],
    [file("a", { kind: "report", last_author: "platform" }), "platform"],
  ])("%#", (item, kind) => {
    expect(authorKind(item, seats)).toBe(kind);
  });
});

describe("excerpts", () => {
  it("cuts long lines and keeps the first lines", () => {
    expect(excerptLines("a\r\nb\nc", 2)).toBe("a\nb");
    expect(excerptLines("x".repeat(10), 1, 4)).toBe("xxxx…");
  });
  it("cuts markdown at a paragraph and closes an open fence", () => {
    const text = `# Title\n\nFirst paragraph.\n\n\`\`\`py\n${"x = 1\n".repeat(40)}\`\`\`\n`;
    const excerpt = markdownExcerpt(text, 60);
    expect(excerpt.startsWith("# Title")).toBe(true);
    expect((excerpt.match(/```/g) ?? []).length % 2).toBe(0);
    expect(markdownExcerpt("---\ntitle: x\n---\nHello", 100)).toBe("Hello");
  });
});
