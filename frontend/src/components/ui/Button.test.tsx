import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { Button, ButtonLink } from "./Button";

describe("<Button>", () => {
  it("renders children and fires onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Save</Button>);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("respects disabled (no onClick fires)", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>Save</Button>);
    await user.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("default type is button (not submit) so it won't accidentally submit forms", () => {
    render(<Button>Action</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("respects explicit type='submit'", () => {
    render(<Button type="submit">Save</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
  });

  it("accepts every documented tone without crashing", () => {
    const tones = ["primary", "secondary", "danger", "ghost"] as const;
    for (const tone of tones) {
      const { unmount } = render(<Button tone={tone}>X</Button>);
      unmount();
    }
  });
});

describe("<ButtonLink>", () => {
  it("renders a <Link> when `to` is set", () => {
    render(
      <MemoryRouter>
        <ButtonLink to="/dashboard">Go</ButtonLink>
      </MemoryRouter>,
    );
    const a = screen.getByRole("link", { name: "Go" });
    expect(a).toHaveAttribute("href", "/dashboard");
  });

  it("renders a plain <a> when `href` is set", () => {
    render(<ButtonLink href="https://example.com">External</ButtonLink>);
    const a = screen.getByRole("link", { name: "External" });
    expect(a).toHaveAttribute("href", "https://example.com");
  });
});
