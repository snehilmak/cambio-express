import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { Badge } from "./Badge";

describe("<Badge>", () => {
  it("renders the count text", () => {
    const { getByText } = render(<Badge>3</Badge>);
    expect(getByText("3")).toBeInTheDocument();
  });

  it("renders dot mode without text + with aria-hidden", () => {
    const { container } = render(<Badge dot tone="success" />);
    const dot = container.querySelector("span");
    expect(dot).not.toBeNull();
    expect(dot).toHaveAttribute("aria-hidden", "true");
    expect(dot?.textContent).toBe("");
  });

  it("accepts a tone prop without crashing", () => {
    // Smoke test for every supported tone.  We don't assert
    // specific colours because they come from CSS vars at runtime.
    const tones = ["neutral", "info", "success", "warning", "error"] as const;
    for (const tone of tones) {
      const { unmount } = render(<Badge tone={tone}>1</Badge>);
      unmount();
    }
  });
});
