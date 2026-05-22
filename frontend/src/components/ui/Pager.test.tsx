import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Pager } from "./Pager";

describe("<Pager>", () => {
  it("renders the page indicator", () => {
    render(<Pager page={2} totalPages={5} onPage={() => {}} />);
    expect(screen.getByText("2 / 5")).toBeInTheDocument();
  });

  it("fires onPage with next page when Next clicked", async () => {
    const user = userEvent.setup();
    const onPage = vi.fn();
    render(<Pager page={2} totalPages={5} onPage={onPage} />);
    await user.click(screen.getByRole("button", { name: /Next/i }));
    expect(onPage).toHaveBeenCalledWith(3);
  });

  it("fires onPage with previous page when Prev clicked", async () => {
    const user = userEvent.setup();
    const onPage = vi.fn();
    render(<Pager page={3} totalPages={5} onPage={onPage} />);
    await user.click(screen.getByRole("button", { name: /Prev/i }));
    expect(onPage).toHaveBeenCalledWith(2);
  });

  it("disables Prev on first page", () => {
    render(<Pager page={1} totalPages={5} onPage={() => {}} />);
    expect(screen.getByRole("button", { name: /Prev/i })).toBeDisabled();
  });

  it("disables Next on last page", () => {
    render(<Pager page={5} totalPages={5} onPage={() => {}} />);
    expect(screen.getByRole("button", { name: /Next/i })).toBeDisabled();
  });

  it("renders nothing when totalPages <= 1 and no leading content", () => {
    const { container } = render(
      <Pager page={1} totalPages={1} onPage={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders leading content even when totalPages <= 1", () => {
    render(
      <Pager
        page={1} totalPages={1} onPage={() => {}}
        leading={<span>Total: $99</span>}
      />,
    );
    expect(screen.getByText("Total: $99")).toBeInTheDocument();
  });
});
