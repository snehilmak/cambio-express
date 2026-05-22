import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Empty, EmptyState } from "./Empty";

describe("<Empty>", () => {
  it("renders children", () => {
    render(<Empty>Nothing to show.</Empty>);
    expect(screen.getByText("Nothing to show.")).toBeInTheDocument();
  });

  it("accepts the error flag without crashing", () => {
    render(<Empty error>Something failed.</Empty>);
    expect(screen.getByText("Something failed.")).toBeInTheDocument();
  });
});

describe("<EmptyState>", () => {
  it("renders the title + body", () => {
    render(
      <EmptyState
        title="No customers yet"
        body="Once you log a transfer with a new sender, they'll appear here."
      />,
    );
    expect(screen.getByText("No customers yet")).toBeInTheDocument();
    expect(screen.getByText(/log a transfer with a new sender/))
      .toBeInTheDocument();
  });

  it("renders the CTA element", () => {
    render(
      <EmptyState
        title="Empty"
        cta={<button>Add one</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Add one" }))
      .toBeInTheDocument();
  });

  it("renders without body / cta when omitted", () => {
    render(<EmptyState title="Just a title" />);
    expect(screen.getByText("Just a title")).toBeInTheDocument();
  });
});
