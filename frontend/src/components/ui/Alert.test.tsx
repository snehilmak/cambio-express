import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Alert } from "./Alert";

describe("<Alert>", () => {
  it("renders children", () => {
    render(<Alert tone="error">Something broke.</Alert>);
    expect(screen.getByText("Something broke.")).toBeInTheDocument();
  });

  it("uses role='alert' for error tone (screen readers interrupt)", () => {
    render(<Alert tone="error">Failure.</Alert>);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("uses role='status' for non-error tones (polite announcement)", () => {
    render(<Alert tone="success">Saved.</Alert>);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("supports every documented tone without crashing", () => {
    const tones = ["info", "success", "warning", "error"] as const;
    for (const tone of tones) {
      const { unmount } = render(<Alert tone={tone}>X</Alert>);
      unmount();
    }
  });
});
