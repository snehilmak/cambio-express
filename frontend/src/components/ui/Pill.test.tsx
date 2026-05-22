import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Pill } from "./Pill";

describe("<Pill>", () => {
  it("renders children", () => {
    render(<Pill tone="success">Active</Pill>);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("supports every documented tone", () => {
    const tones = [
      "neutral", "accent", "negative", "warning", "info", "success",
    ] as const;
    for (const tone of tones) {
      const { unmount } = render(<Pill tone={tone}>x</Pill>);
      unmount();
    }
  });
});
