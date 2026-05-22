import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Checkbox } from "./Checkbox";

describe("<Checkbox>", () => {
  it("renders the label as part of the click target", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Checkbox checked={false} onChange={onChange}>
        Block transfers outside hours
      </Checkbox>,
    );
    // Click the LABEL text (not the input) — the label wrapper
    // should route the click into the input's onChange.
    await user.click(screen.getByText("Block transfers outside hours"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("calls onChange with the new boolean value on click", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Checkbox checked={true} onChange={onChange}>Toggle</Checkbox>,
    );
    await user.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("is uncontrolled when defaultChecked is set", () => {
    render(<Checkbox defaultChecked>Uncontrolled</Checkbox>);
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("respects disabled", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Checkbox checked={false} onChange={onChange} disabled>
        Locked
      </Checkbox>,
    );
    await user.click(screen.getByRole("checkbox"));
    expect(onChange).not.toHaveBeenCalled();
  });
});
