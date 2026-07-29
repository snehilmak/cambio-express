import { useState } from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PhoneField } from "./PhoneField";

// Controlled harness so the emitted E.164 round-trips back into `value`,
// mirroring how a real form wires PhoneField.
function Harness({ initial = "" }: { initial?: string }) {
  const [v, setV] = useState(initial);
  return (
    <>
      <PhoneField value={v} onChange={setV} />
      <output data-testid="val">{v}</output>
    </>
  );
}

describe("<PhoneField>", () => {
  it("emits a valid US E.164 as the operator types a 10-digit number", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByRole("textbox"), "3105551234");
    expect(screen.getByTestId("val").textContent).toBe("+13105551234");
  });

  it("hydrates an incoming E.164 value into country + national format", () => {
    render(<Harness initial="+13105551234" />);
    // National formatting for display.
    expect(screen.getByRole("textbox")).toHaveValue("(310) 555-1234");
    // Country picker resolves to US.
    expect(screen.getByLabelText("Country code")).toHaveValue("US");
  });

  it("switching country re-bases the calling code", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.selectOptions(screen.getByLabelText("Country code"), "MX");
    await user.type(screen.getByRole("textbox"), "5555555555");
    expect(screen.getByTestId("val").textContent?.startsWith("+52")).toBe(true);
  });

  it("offers the country picker with a calling code label", () => {
    render(<Harness />);
    const select = screen.getByLabelText("Country code");
    expect(select).toBeInTheDocument();
    // US default option shows its flag + calling code.
    expect(screen.getByRole("option", { name: "🇺🇸 +1" })).toBeInTheDocument();
  });
});
