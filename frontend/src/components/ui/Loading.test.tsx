import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Loading } from "./Loading";

describe("<Loading>", () => {
  it("renders the default 'Loading…' label", () => {
    render(<Loading />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders a custom label when provided", () => {
    render(<Loading label="Fetching transfers" />);
    expect(screen.getByText("Fetching transfers")).toBeInTheDocument();
  });

  it("uses aria-live='polite' so assistive tech announces without interrupting", () => {
    const { container } = render(<Loading />);
    const node = container.querySelector("[aria-live='polite']");
    expect(node).not.toBeNull();
  });
});
