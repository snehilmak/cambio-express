import { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MoneyInput } from "./MoneyInput";

// MoneyInput renders its label as a sibling span inside a wrapping
// <label>, plus a `$` prefix span and the <input>.  That means the
// label's text content isn't just the prop string, so
// getByLabelText("Cash") doesn't match — we use getByRole("textbox")
// instead since each test renders exactly one input.
function input() {
  return screen.getByRole("textbox") as HTMLInputElement;
}

/** Stateful wrapper for typing-accumulation tests.  MoneyInput is a
 *  fully-controlled component — without state lifted up, every
 *  keystroke gets clobbered back to the initial `value` prop on
 *  re-render. */
function Controlled({
  initial = 0, onSettled,
}: { initial?: number; onSettled?: (v: number) => void }) {
  const [v, setV] = useState(initial);
  return (
    <MoneyInput
      value={v}
      onChange={(next) => { setV(next); onSettled?.(next); }}
      label="Cash"
    />
  );
}

describe("<MoneyInput>", () => {
  it("renders 0 as empty input (not '0' or '0.00')", () => {
    render(<MoneyInput value={0} onChange={() => {}} label="Cash" />);
    expect(input().value).toBe("");
  });

  it("renders whole numbers without trailing .00", () => {
    render(<MoneyInput value={123} onChange={() => {}} label="Cash" />);
    expect(input().value).toBe("123");
  });

  it("renders non-whole numbers with trimmed decimals (12.5 not 12.50)", () => {
    render(<MoneyInput value={12.5} onChange={() => {}} label="Cash" />);
    expect(input().value).toBe("12.5");
  });

  it("accumulates typed digits via the controlled state contract", async () => {
    const user = userEvent.setup();
    const onSettled = vi.fn();
    render(<Controlled onSettled={onSettled} />);
    await user.type(input(), "12");
    // Each keystroke goes through the parent's setState → re-renders
    // MoneyInput with the new value.  Final onChange call should be
    // 12 (one + two = "12" parsed).
    expect(onSettled).toHaveBeenLastCalledWith(12);
    expect(input().value).toBe("12");
  });

  it("fires onChange(0) when input is cleared (empty = zero contract)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<MoneyInput value={42} onChange={onChange} label="Cash" />);
    await user.clear(input());
    expect(onChange).toHaveBeenLastCalledWith(0);
  });

  it("strips non-numeric characters as the user types", async () => {
    const user = userEvent.setup();
    const onSettled = vi.fn();
    render(<Controlled onSettled={onSettled} />);
    // Typing "abc1.2.3$de" — letters + duplicate dots + currency
    // symbols all stripped.  Final value is 1.23 (one decimal point).
    await user.type(input(), "abc1.2.3$de");
    expect(onSettled).toHaveBeenLastCalledWith(1.23);
  });

  it("uses inputMode='decimal' (mobile keypad) and type='text' (no spinner arrows)", () => {
    render(<MoneyInput value={0} onChange={() => {}} label="Cash" />);
    expect(input()).toHaveAttribute("inputMode", "decimal");
    expect(input()).toHaveAttribute("type", "text");
  });

  it("renders the default '$' prefix", () => {
    render(<MoneyInput value={0} onChange={() => {}} label="Cash" />);
    expect(screen.getByText("$")).toBeInTheDocument();
  });

  it("drops the prefix when prefix=''", () => {
    render(<MoneyInput value={0} onChange={() => {}} label="Pct" prefix="" />);
    expect(screen.queryByText("$")).toBeNull();
  });

  it("respects disabled (no onChange fires + aria-disabled)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <MoneyInput value={5} onChange={onChange} label="Cash" disabled />,
    );
    await user.type(input(), "9");
    expect(onChange).not.toHaveBeenCalled();
    expect(input()).toBeDisabled();
  });

  it("renders error message + sets aria-invalid", () => {
    render(
      <MoneyInput
        value={0} onChange={() => {}}
        label="Cash" error="Must be positive"
      />,
    );
    expect(screen.getByText("Must be positive")).toBeInTheDocument();
    expect(input()).toHaveAttribute("aria-invalid", "true");
  });

  it("renders hint when provided + no error", () => {
    render(
      <MoneyInput
        value={0} onChange={() => {}}
        label="Cash" hint="Counted at close"
      />,
    );
    expect(screen.getByText("Counted at close")).toBeInTheDocument();
  });

  it("error replaces hint (both shouldn't render together)", () => {
    render(
      <MoneyInput
        value={0} onChange={() => {}}
        label="Cash" hint="Counted at close" error="Bad value"
      />,
    );
    expect(screen.getByText("Bad value")).toBeInTheDocument();
    expect(screen.queryByText("Counted at close")).toBeNull();
  });

  it("ignores commas / negative signs (positive-only contract)", async () => {
    const user = userEvent.setup();
    const onSettled = vi.fn();
    render(<Controlled onSettled={onSettled} />);
    await user.type(input(), "-1,000");
    // Commas + dashes get stripped; final value is 1000.
    expect(onSettled).toHaveBeenLastCalledWith(1000);
  });
});
