import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { Avatar } from "./Avatar";

describe("<Avatar>", () => {
  it("renders the first character of name, uppercased", () => {
    const { getByText } = render(<Avatar name="marcela" />);
    expect(getByText("M")).toBeInTheDocument();
  });

  it("falls back to '·' when name is empty", () => {
    const { getByText } = render(<Avatar name="" />);
    expect(getByText("·")).toBeInTheDocument();
  });

  it("hides the initial from screen readers", () => {
    const { getByText } = render(<Avatar name="alice" />);
    expect(getByText("A")).toHaveAttribute("aria-hidden", "true");
  });

  it("exposes role=img + aria-label when provided", () => {
    const { getByRole } = render(
      <Avatar name="bob" aria-label="Bob Smith" />,
    );
    expect(getByRole("img", { name: "Bob Smith" })).toBeInTheDocument();
  });

  it("renders no initial text when src is set", () => {
    const { queryByText } = render(
      <Avatar name="carol" src="/avatar.png" />,
    );
    // The initial 'C' should NOT render — src takes over.
    expect(queryByText("C")).toBeNull();
  });
});
