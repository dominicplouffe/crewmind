import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

afterEach(cleanup);

function setup(overrides: Partial<Parameters<typeof Composer>[0]> = {}): {
  box: HTMLTextAreaElement;
  onSend: ReturnType<typeof vi.fn>;
  onInterrupt: ReturnType<typeof vi.fn>;
  onFiles: ReturnType<typeof vi.fn>;
} {
  const onSend = vi.fn();
  const onInterrupt = vi.fn();
  const onFiles = vi.fn();
  render(
    <Composer
      commands={{ "/hold": "Hold a project.", "/help": "List the commands." }}
      mentions={[{ name: "CEO", detail: "Agent" }]}
      history={["first message", "second message"]}
      replyTo={null}
      replying={false}
      uploads={[]}
      onSend={onSend}
      onCancelReply={() => {}}
      onInterrupt={onInterrupt}
      onFiles={onFiles}
      onDismissUpload={() => {}}
      {...overrides}
    />,
  );
  return { box: screen.getByLabelText("Message") as HTMLTextAreaElement, onSend, onInterrupt, onFiles };
}

function type(box: HTMLTextAreaElement, value: string): void {
  box.setSelectionRange(value.length, value.length);
  fireEvent.change(box, { target: { value, selectionStart: value.length } });
}

describe("Composer (CHAT-4)", () => {
  it("sends on Enter and keeps a new line on Shift+Enter", () => {
    const { box, onSend } = setup();
    type(box, "hello");
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(box.value).toBe("");
  });

  it("lists slash commands and completes the chosen one", () => {
    const { box, onSend } = setup();
    type(box, "/h");
    const options = screen.getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["/helpList the commands.", "/holdHold a project."]);
    expect(options[0]?.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(box.value).toBe("/hold ");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("completes an @ mention with Tab", () => {
    const { box } = setup();
    type(box, "ask @c");
    expect(screen.getByRole("option").textContent).toContain("@CEO");
    fireEvent.keyDown(box, { key: "Tab" });
    expect(box.value).toBe("ask @CEO ");
  });

  it("recalls earlier messages with the Up and Down arrows", () => {
    const { box } = setup();
    fireEvent.keyDown(box, { key: "ArrowUp" });
    expect(box.value).toBe("second message");
    fireEvent.keyDown(box, { key: "ArrowUp" });
    expect(box.value).toBe("first message");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(box.value).toBe("second message");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(box.value).toBe("");
  });

  it("loads the last message for editing and resending", () => {
    const { box } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Edit and resend last" }));
    expect(box.value).toBe("second message");
  });

  it("interrupts a reply on Esc only while one is being written", () => {
    const idle = setup();
    fireEvent.keyDown(idle.box, { key: "Escape" });
    expect(idle.onInterrupt).not.toHaveBeenCalled();
    cleanup();
    const busy = setup({ replying: true });
    fireEvent.keyDown(busy.box, { key: "Escape" });
    expect(busy.onInterrupt).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Stop reply" }));
    expect(busy.onInterrupt).toHaveBeenCalledTimes(2);
  });

  it("takes pasted files as attachments", () => {
    const { box, onFiles } = setup();
    const file = new File(["x"], "shot.png", { type: "image/png" });
    fireEvent.paste(box, { clipboardData: { files: [file] } });
    expect(onFiles).toHaveBeenCalledWith([file]);
  });
});
