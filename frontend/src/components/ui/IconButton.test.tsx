import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IconButton } from "./IconButton";

describe("<IconButton>", () => {
  it("renders an accessible label via aria-label", () => {
    render(<IconButton aria-label="Delete row">×</IconButton>);
    expect(screen.getByRole("button", { name: "Delete row" }))
      .toBeInTheDocument();
  });

  it("fires onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <IconButton aria-label="Close" onClick={onClick}>×</IconButton>,
    );
    await user.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
  });

  it("respects disabled", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <IconButton aria-label="Close" disabled onClick={onClick}>×</IconButton>,
    );
    await user.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("default type is button", () => {
    render(<IconButton aria-label="X">×</IconButton>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });
});
