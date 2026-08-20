import { describe, it, expect } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { InfoTip } from "./InfoTip";

describe("<InfoTip>", () => {
  it("renders a labelled icon button with no visible tip when idle", () => {
    render(<InfoTip text="Explains the thing." />);
    expect(screen.getByRole("button", { name: "More info" })).toBeTruthy();
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("reveals the explanatory text on keyboard focus", async () => {
    const user = userEvent.setup();
    render(<InfoTip text="Auto-carried from yesterday." />);
    await act(async () => {
      await user.tab();
    });
    await waitFor(() => {
      expect(screen.getByRole("tooltip")).toHaveTextContent(
        "Auto-carried from yesterday.",
      );
    });
  });

  it("uses a custom accessible label when given", () => {
    render(<InfoTip text="x" label="About forward balance" />);
    expect(
      screen.getByRole("button", { name: "About forward balance" }),
    ).toBeTruthy();
  });

  it("never submits a surrounding form", () => {
    // type="button" — rendering inside a <form> must not wire it
    // as the implicit submit button.
    render(
      <form>
        <InfoTip text="x" />
      </form>,
    );
    expect(
      screen.getByRole("button", { name: "More info" }),
    ).toHaveAttribute("type", "button");
  });
});
