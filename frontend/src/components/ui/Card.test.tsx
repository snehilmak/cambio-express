import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Card } from "./Card";

describe("<Card>", () => {
  it("renders children", () => {
    render(<Card>Body content</Card>);
    expect(screen.getByText("Body content")).toBeInTheDocument();
  });

  it("uses a <section> element so screen readers get the landmark", () => {
    const { container } = render(<Card>X</Card>);
    expect(container.querySelector("section")).not.toBeNull();
  });

  it("applies the ds-card class", () => {
    const { container } = render(<Card>X</Card>);
    expect(container.querySelector(".ds-card")).not.toBeNull();
  });

  it("adds ds-card--interactive when interactive=true", () => {
    const { container } = render(<Card interactive>X</Card>);
    expect(container.querySelector(".ds-card--interactive")).not.toBeNull();
  });

  it("merges an extra className without clobbering ds-card", () => {
    const { container } = render(<Card className="custom-thing">X</Card>);
    const card = container.querySelector("section");
    expect(card?.className).toContain("ds-card");
    expect(card?.className).toContain("custom-thing");
  });
});
