import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Switch } from "./Switch";

describe("<Switch>", () => {
  it("renders with role='switch'", () => {
    render(<Switch checked={false} onChange={() => {}}>Notifications</Switch>);
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });

  it("calls onChange with the new boolean on click", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange}>Toggle</Switch>);
    await user.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("clicking the label flips the switch (whole row is hit target)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Switch checked={true} onChange={onChange}>Enforce</Switch>);
    await user.click(screen.getByText("Enforce"));
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("is uncontrolled when defaultChecked is set", () => {
    render(<Switch defaultChecked>Uncontrolled</Switch>);
    expect(screen.getByRole("switch")).toBeChecked();
  });

  it("respects disabled", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Switch checked={false} onChange={onChange} disabled>Locked</Switch>,
    );
    await user.click(screen.getByRole("switch"));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("renders without a label when children is omitted", () => {
    render(<Switch checked={false} onChange={() => {}} />);
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });
});
