import { describe, expect, it } from "vitest";
import { parseCsv } from "./csv";

describe("parseCsv", () => {
  it("parses plain rows", () => {
    expect(parseCsv("a,b\n1,2\n")).toEqual([["a", "b"], ["1", "2"]]);
  });

  it("handles quoted fields with commas, doubled quotes and line breaks", () => {
    expect(parseCsv('name,quote\nAda,"Hello, ""world"""\nBo,"two\nlines"')).toEqual([
      ["name", "quote"],
      ["Ada", 'Hello, "world"'],
      ["Bo", "two\nlines"],
    ]);
  });

  it("keeps empty fields and handles CRLF and a byte-order mark", () => {
    expect(parseCsv("﻿a,,c\r\n,,\r\n")).toEqual([["a", "", "c"], ["", "", ""]]);
  });

  it("returns nothing for empty text and supports other delimiters", () => {
    expect(parseCsv("")).toEqual([]);
    expect(parseCsv("a\tb", "\t")).toEqual([["a", "b"]]);
  });
});
