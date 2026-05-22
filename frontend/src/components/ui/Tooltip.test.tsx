import { describe, it, expect } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Tooltip } from "./Tooltip";

describe("<Tooltip>", () => {
  it("does not render the tip when idle", () => {
    render(
      <Tooltip label="Helpful">
        <button>Hover me</button>
      </Tooltip>,
    );
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("shows the tip on focus", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Helpful" delayMs={0}>
        <button>Trigger</button>
      </Tooltip>,
    );
    await act(async () => {
      await user.tab(); // moves focus to the button
    });
    await waitFor(() => {
      expect(screen.getByRole("tooltip")).toHaveTextContent("Helpful");
    });
  });

  it("hides the tip on blur", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Helpful" delayMs={0}>
        <button>Trigger</button>
      </Tooltip>,
    );
    await act(async () => {
      await user.tab();
    });
    await waitFor(() => {
      expect(screen.getByRole("tooltip")).toBeInTheDocument();
    });
    await act(async () => {
      await user.tab(); // moves focus away
    });
    await waitFor(() => {
      expect(screen.queryByRole("tooltip")).toBeNull();
    });
  });

  it("wires aria-describedby on the trigger to the tip's id", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Helpful" delayMs={0}>
        <button>Trigger</button>
      </Tooltip>,
    );
    await act(async () => {
      await user.tab();
    });
    const tip = await waitFor(() => screen.getByRole("tooltip"));
    const trigger = screen.getByRole("button");
    expect(trigger.getAttribute("aria-describedby"))
      .toContain(tip.getAttribute("id"));
  });
});
