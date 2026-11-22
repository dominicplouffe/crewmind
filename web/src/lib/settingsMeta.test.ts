/**
 * Every governed setting in Appendix A has a plain label, help and a control; ranges are read
 * from the registry's own strings; typed values convert back to the stored value exactly.
 */
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DESCRIBED_SETTINGS,
  durationUnitsFor,
  editStateOf,
  formatDuration,
  formatSetting,
  groupSettings,
  humanizeName,
  metaOf,
  parseAllowed,
  parseTokens,
  rangeText,
  valueOf,
} from "./settingsMeta";

/** Appendix A, found from the web app's folder (where vitest runs) or the repository root. */
const APPENDIX = ["../docs/spec/appendix-a-settings.md", "docs/spec/appendix-a-settings.md"]
  .map((path) => resolve(process.cwd(), path))
  .find((path) => existsSync(path));
const appendix = APPENDIX ? readFileSync(APPENDIX, "utf8") : "";

/** The rows of the governed-settings table: name, default, range. */
const ROWS = appendix
  .split("\n")
  .map((line) => /^\| `([a-z][a-z0-9_.]*)` \| (.*?) \| (.*?) \| (project|install|person) \|/.exec(line))
  .filter((match): match is RegExpExecArray => match !== null)
  .map((match) => ({ name: match[1] ?? "", allowed: match[3] ?? "", scope: match[4] ?? "" }));

/** Units the server reports for a setting, by the control kind (settings.operations UNITS). */
const UNIT_OF: Record<string, string> = { duration: "seconds", tokens: "tokens", bytes: "bytes", percent: "percent" };

describe("every setting in Appendix A is described", () => {
  it("finds the settings table", () => {
    expect(ROWS.length).toBeGreaterThan(80);
  });

  it.each(ROWS.map((row) => [row.name]))("%s has a label, help and a known control", (name) => {
    const meta = metaOf(name);
    expect(meta.described).toBe(true);
    expect(meta.label).not.toBe("");
    if (name.includes(".")) expect(meta.label).not.toContain(name);
    expect(meta.help.length).toBeGreaterThan(10);
    expect(meta.group).not.toBe("other");
    if (meta.kind === "choice") expect(meta.choices.length).toBeGreaterThan(1);
  });

  it("describes nothing that is not in Appendix A", () => {
    const names = new Set(ROWS.map((row) => row.name));
    expect(DESCRIBED_SETTINGS.filter((name) => !names.has(name))).toEqual([]);
  });

  it("falls back to a humanised label for a setting it does not know", () => {
    const meta = metaOf("widget.max_frobs", null, 3);
    expect(meta.described).toBe(false);
    expect(meta.label).toBe("Widget max frobs");
    expect(meta.kind).toBe("number");
    expect(meta.group).toBe("other");
    expect(humanizeName("a2a.enabled")).toBe("A2a enabled");
  });
});

describe("allowed ranges are read from the registry's strings", () => {
  it.each([
    ["10–360 min", "seconds", { min: 600, max: 21600, offAtZero: false }],
    ["0 (off)–50%", "percent", { min: 0, max: 50, offAtZero: true }],
    ["0 (off) or 100k–50M", "tokens", { min: 100000, max: 50000000, offAtZero: true }],
    ["1M or more", "tokens", { min: 1000000, offAtZero: false }],
    ["1 MB–2 GB", "bytes", { min: 1048576, max: 2147483648, offAtZero: false }],
    ["4 h–14 days", "seconds", { min: 14400, max: 1209600, offAtZero: false }],
    ["10 s–10 min", "seconds", { min: 10, max: 600, offAtZero: false }],
    ["1 day–forever", "seconds", { min: 86400, max: undefined, offAtZero: false }],
    ["2,000–20,000", "tokens", { min: 2000, max: 20000, offAtZero: false }],
    ["off, or 1–4 slots a day", null, { min: 1, max: 4, offAtZero: false }],
    ["0 (off)–7 days", "seconds", { min: 0, max: 604800, offAtZero: true }],
    ["1–30 days", "minutes", { min: 1440, max: 43200, offAtZero: false }],
    ["IANA timezone name", null, { offAtZero: false }],
    ["Weekly: 0–6, 0 = Monday (ISO). Monthly and quarterly: 1–28", null, { offAtZero: false }],
    ["", null, { offAtZero: false }],
  ])("%s", (allowed, unit, expected) => {
    expect(parseAllowed(allowed, unit)).toEqual(expected);
  });

  it("reads every range in Appendix A without throwing, and never upside down", () => {
    for (const row of ROWS) {
      const meta = metaOf(row.name);
      const range = parseAllowed(row.allowed, UNIT_OF[meta.kind] ?? null);
      if (range.min !== undefined && range.max !== undefined) expect(range.min).toBeLessThanOrEqual(range.max);
    }
  });
});

describe("values are shown in plain units", () => {
  it.each([
    ["run.timeout", 5400, "90 minutes"],
    ["heartbeat.every", 21600, "6 hours"],
    ["explore.timebox", 604800, "7 days"],
    ["run.max_tokens", 3000000, "3M tokens"],
    ["run.max_tokens", 0, "No limit"],
    ["budget.warn_at", 80, "80%"],
    ["budget.ceo_reserve", 0, "Off"],
    ["upload.max_size", 104857600, "100 MB"],
    ["storage.quota", 21474836480, "20 GB"],
    ["run.concurrency", 4, "4 runs"],
    ["quality", "best", "Best quality"],
    ["alerts.level", "decisions_and_alarms", "Decisions and alarms"],
    ["review.independent", true, "On"],
    ["correction.ttl", "forever", "Forever"],
    ["report.cadence", "off", "Off"],
  ] as const)("%s = %s → %s", (name, value, text) => {
    const meta = metaOf(name);
    const range = parseAllowed(ROWS.find((row) => row.name === name)?.allowed, UNIT_OF[meta.kind] ?? null);
    expect(formatSetting(meta, value, range)).toBe(text);
  });

  it("says the range in display units", () => {
    const meta = metaOf("run.timeout");
    expect(rangeText(meta, parseAllowed("10–360 min", "seconds"))).toBe("10 minutes to 6 hours");
    expect(rangeText(metaOf("budget.tokens"), parseAllowed("1M or more", "tokens"))).toBe("1M tokens or more");
    expect(formatDuration(90)).toBe("90 seconds");
  });

  it("offers the units that fit the range", () => {
    expect(durationUnitsFor(parseAllowed("10–360 min", "seconds"))).toEqual(["minutes", "hours"]);
    expect(durationUnitsFor(parseAllowed("10 s–10 min", "seconds"))).toEqual(["seconds", "minutes"]);
    expect(durationUnitsFor(parseAllowed("1–90 days", "seconds"))).toEqual(["days"]);
  });
});

describe("typed values convert back to the stored value", () => {
  const STORED: [string, unknown][] = [
    ["run.timeout", 5400],
    ["run.timeout", 600],
    ["stall.after", 3600],
    ["bet.window", 172800],
    ["rehearsal.max_seconds", 60],
    ["alerts.grace", 0],
    ["alerts.grace", 5400],
    ["run.max_tokens", 3000000],
    ["run.max_tokens", 0],
    ["run.max_tokens", 150000],
    ["budget.tokens", 20000000],
    ["memory.pinned_project_tokens", 6000],
    ["upload.max_size", 104857600],
    ["storage.quota", 21474836480],
    ["upload.max_size", 1572864000],
    ["budget.warn_at", 80],
    ["run.concurrency", 4],
    ["spend.monthly_cap", 512.5],
    ["quality", "balanced"],
    ["review.independent", false],
    ["review.independent", true],
    ["correction.ttl", "forever"],
    ["correction.ttl", 2592000],
    ["report.cadence", "off"],
    ["report.cadence", 2],
    ["brief.time", "08:00"],
    ["brief.time", "off"],
    ["spend.currency", "EUR"],
    ["otel.endpoint", "none"],
    ["otel.endpoint", "https://otel.example.com:4318"],
    ["cycle.due_time", "cycle_end"],
    ["person.timezone", "Europe/Berlin"],
  ];

  it.each(STORED)("%s = %s round-trips", (name, value) => {
    const meta = metaOf(name);
    const range = parseAllowed(ROWS.find((row) => row.name === name)?.allowed, UNIT_OF[meta.kind] ?? null);
    expect(valueOf(meta, range, editStateOf(meta, range, value))).toEqual({ ok: true, value });
  });

  it("shows run.timeout in minutes, and converts minutes and hours to seconds", () => {
    const meta = metaOf("run.timeout");
    const range = parseAllowed("10–360 min", "seconds");
    expect(editStateOf(meta, range, 5400)).toEqual({ text: "90", unit: "minutes", special: false });
    expect(valueOf(meta, range, { text: "2", unit: "hours", special: false })).toEqual({ ok: true, value: 7200 });
    expect(valueOf(meta, range, { text: "1.5", unit: "hours", special: false })).toEqual({ ok: true, value: 5400 });
  });

  it("refuses values outside the range, in display units", () => {
    const meta = metaOf("run.timeout");
    const range = parseAllowed("10–360 min", "seconds");
    expect(valueOf(meta, range, { text: "7", unit: "hours", special: false })).toEqual({
      ok: false,
      error: "Enter a value from 10 minutes to 6 hours.",
    });
    expect(valueOf(meta, range, { text: "soon", unit: "minutes", special: false }).ok).toBe(false);
    const tokens = metaOf("run.max_tokens");
    const tokenRange = parseAllowed("0 (off) or 100k–50M", "tokens");
    expect(valueOf(tokens, tokenRange, { text: "50k", unit: "", special: false }).ok).toBe(false);
    expect(valueOf(tokens, tokenRange, { text: "0", unit: "", special: false })).toEqual({ ok: true, value: 0 });
    expect(valueOf(metaOf("spend.currency"), { offAtZero: false }, { text: "euro", unit: "", special: false }).ok).toBe(false);
    expect(valueOf(metaOf("run.concurrency"), parseAllowed("1–16"), { text: "2.5", unit: "", special: false }).ok).toBe(false);
  });

  it.each([
    ["3M", 3000000],
    ["500k", 500000],
    ["1.5m", 1500000],
    ["3,000,000", 3000000],
    ["2000 tokens", 2000],
    ["three", null],
  ])("reads %s as %s tokens", (text, tokens) => {
    expect(parseTokens(text)).toBe(tokens);
  });
});

describe("grouping", () => {
  it("groups settings in a fixed order and keeps unknown ones under Other", () => {
    const groups = groupSettings([
      { name: "run.timeout", unit: "seconds", value: 5400 },
      { name: "quality", unit: null, value: "fast" },
      { name: "widget.size", unit: null, value: 2 },
      { name: "budget.tokens", unit: "tokens", value: 1 },
    ]);
    expect(groups.map((group) => group.group)).toEqual(["quality", "budget", "runs", "other"]);
  });
});
