import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { Progress } from "./Progress";

describe("<Progress>", () => {
  it("renders with role=progressbar + a default aria-label", () => {
    const { getByRole } = render(<Progress value={50} />);
    expect(getByRole("progressbar", { name: "Progress" }))
      .toBeInTheDocument();
  });

  it("forwards a custom aria-label", () => {
    const { getByRole } = render(<Progress value={50} label="Uploading" />);
    expect(getByRole("progressbar", { name: "Uploading" }))
      .toBeInTheDocument();
  });

  it("clamps + rounds the value to 0-100", () => {
    const { getByRole, rerender } = render(<Progress value={120} />);
    expect(getByRole("progressbar"))
      .toHaveAttribute("aria-valuenow", "100");
    rerender(<Progress value={-5} />);
    expect(getByRole("progressbar"))
      .toHaveAttribute("aria-valuenow", "0");
    rerender(<Progress value={42.7} />);
    expect(getByRole("progressbar"))
      .toHaveAttribute("aria-valuenow", "43");
  });

  it("drops aria-valuenow in indeterminate mode (value omitted)", () => {
    const { getByRole } = render(<Progress />);
    const bar = getByRole("progressbar");
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(bar).not.toHaveAttribute("aria-valuemin");
  });
});
