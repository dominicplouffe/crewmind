import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { StartDialog } from "./StartDialog";

afterEach(cleanup);
beforeAll(() => {
  // jsdom has no showModal.
  HTMLDialogElement.prototype.showModal ??= function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
});

const waiting = [{ text: "The secret wordpress is missing.", seats: ["Ada"] }];

describe("StartDialog (CON-5, PRJ-1)", () => {
  it("names what is missing and who waits for it", () => {
    render(<StartDialog waiting={waiting} onStartWithout={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText("The secret wordpress is missing.")).toBeTruthy();
    expect(screen.getByText("Waits: Ada")).toBeTruthy();
    expect(screen.getByText(/1 agent needs/)).toBeTruthy();
  });

  it("starts without it only when asked, and Not now starts nothing", async () => {
    const onStartWithout = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(<StartDialog waiting={waiting} onStartWithout={onStartWithout} onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(onClose).toHaveBeenCalled();
    expect(onStartWithout).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Start without it" }));
    await waitFor(() => expect(onStartWithout).toHaveBeenCalledTimes(1));
  });

  it("says a need is added under other names, without starting by itself", async () => {
    const onMarkDone = vi.fn().mockResolvedValue(undefined);
    const onStartWithout = vi.fn();
    const need = { kind: "secret", name: "wordpress" };
    render(
      <StartDialog
        waiting={[{ ...waiting[0], need }, { text: "Ada cannot run: no model.", seats: ["Ada"], need: null }]}
        onStartWithout={onStartWithout}
        onMarkDone={onMarkDone}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getAllByRole("button", { name: /^It's added/ })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "It's added: wordpress" }));
    await waitFor(() => expect(onMarkDone).toHaveBeenCalledWith(need));
    expect(onStartWithout).not.toHaveBeenCalled();
  });
});
