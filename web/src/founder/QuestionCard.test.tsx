import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Question } from "./logic";
import { QuestionCard } from "./QuestionCard";

afterEach(cleanup);

function question(extra: Partial<Question> = {}): Question {
  return {
    id: 4,
    settles: "finish_line",
    text: "What record shows it is finished?",
    options: ["A draft", "The signed proof"],
    recommended: 1,
    changes: "the finish line",
    ...extra,
  };
}

function show(asked: Question): ReturnType<typeof vi.fn> {
  const onAnswer = vi.fn().mockResolvedValue(true);
  render(<QuestionCard question={asked} busy={false} onAnswer={onAnswer} />);
  return onAnswer;
}

describe("QuestionCard (FND-3)", () => {
  it("marks the recommended option, focuses it, and Enter accepts it", async () => {
    const onAnswer = show(question());
    const recommended = screen.getByRole("button", { name: /The signed proof.*Recommended/ });
    expect(document.activeElement).toBe(recommended);
    expect(screen.getByText("What this changes: the finish line")).toBeTruthy();
    await userEvent.keyboard("{Enter}");
    expect(onAnswer).toHaveBeenCalledWith(4, "b");
  });

  it("sends another option by its letter", async () => {
    const onAnswer = show(question());
    await userEvent.click(screen.getByRole("button", { name: "a. A draft" }));
    expect(onAnswer).toHaveBeenCalledWith(4, "a");
  });

  it("sends the person's own words, and an empty box accepts the recommendation", async () => {
    const onAnswer = show(question());
    const box = screen.getByLabelText<HTMLInputElement>("Or answer in your own words");
    await userEvent.type(box, "The printer's receipt{Enter}");
    expect(onAnswer).toHaveBeenLastCalledWith(4, "The printer's receipt");
    await waitFor(() => expect(box.value).toBe(""));
    await userEvent.click(screen.getByRole("button", { name: "Use the recommended answer" }));
    expect(onAnswer).toHaveBeenLastCalledWith(4, "");
  });

  it("marks nothing and accepts nothing by Enter when the Founder recommends nothing (who pays)", async () => {
    const onAnswer = show(question({ settles: "who_pays", options: ["main", "spare"], recommended: null }));
    expect(screen.queryByText("Recommended")).toBeNull();
    expect(document.activeElement).toBe(screen.getByText("What record shows it is finished?"));
    await userEvent.keyboard("{Enter}");
    expect(onAnswer).not.toHaveBeenCalled();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Send my answer" }).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "b. spare" }));
    expect(onAnswer).toHaveBeenCalledWith(4, "b");
  });
});
