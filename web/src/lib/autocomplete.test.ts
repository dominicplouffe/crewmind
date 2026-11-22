import { describe, expect, it } from "vitest";
import { applyCompletion, commandCompletion, findCompletion, isCommand, mentionCompletion } from "./autocomplete";

const commands = { "/hold": "Hold a project.", "/help": "List the commands.", "/resume": "Resume a project." };
const targets = [
  { name: "CEO", detail: "Agent" },
  { name: "Casey", detail: "Agent" },
  { name: "research", detail: "Team" },
];

describe("slash command completion", () => {
  it("offers every command after a lone slash, in order", () => {
    expect(commandCompletion("/", 1, commands)?.options.map((o) => o.value)).toEqual(["/help", "/hold", "/resume"]);
  });

  it("narrows as the person types, ignoring case", () => {
    const completion = commandCompletion("/HO", 3, commands);
    expect(completion?.options).toEqual([{ value: "/hold", detail: "Hold a project." }]);
  });

  it("offers nothing mid-message, after the command word, or for unknown commands", () => {
    expect(commandCompletion("say /ho", 7, commands)).toBeNull();
    expect(commandCompletion("/hold until 5pm", 12, commands)).toBeNull();
    expect(commandCompletion("/zzz", 4, commands)).toBeNull();
  });

  it("replaces the typed word and adds a space", () => {
    const completion = commandCompletion("/ho", 3, commands);
    const option = completion?.options[0];
    expect(completion && option && applyCompletion("/ho", completion, option)).toEqual({ text: "/hold ", cursor: 6 });
  });
});

describe("mention completion", () => {
  it("offers agents and teams after @", () => {
    expect(mentionCompletion("ask @", 5, targets)?.options.map((o) => o.value)).toEqual(["@CEO", "@Casey", "@research"]);
    expect(mentionCompletion("@c", 2, targets)?.options.map((o) => o.value)).toEqual(["@CEO", "@Casey"]);
    expect(mentionCompletion("ask @res", 8, targets)?.options).toEqual([{ value: "@research", detail: "Team" }]);
  });

  it("does not trigger inside an email address or with no match", () => {
    expect(mentionCompletion("mail dom@c", 10, targets)).toBeNull();
    expect(mentionCompletion("@zed", 4, targets)).toBeNull();
  });

  it("replaces only the mention being typed and keeps the rest", () => {
    const text = "ask @ce about it";
    const completion = mentionCompletion(text, 7, targets);
    const option = completion?.options[0];
    expect(completion && option && applyCompletion(text, completion, option)).toEqual({
      text: "ask @CEO about it",
      cursor: 9,
    });
  });
});

describe("findCompletion and isCommand", () => {
  it("prefers the command at the start, then mentions", () => {
    expect(findCompletion("/re", 3, commands, targets)?.kind).toBe("command");
    expect(findCompletion("/do @ce", 7, commands, targets)?.kind).toBe("mention");
    expect(findCompletion("plain text", 5, commands, targets)).toBeNull();
  });

  it("treats a message that starts with a slash as a command", () => {
    expect(isCommand("/hold")).toBe(true);
    expect(isCommand("  /status")).toBe(true);
    expect(isCommand("and/or")).toBe(false);
  });
});
