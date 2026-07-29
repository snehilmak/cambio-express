import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import StoreGate from "./StoreGate";

function renderGate(props: Partial<React.ComponentProps<typeof StoreGate>> = {}) {
  const onSignOut = vi.fn();
  render(
    <MemoryRouter>
      <StoreGate
        reason="subscription"
        storeName="Cambio Express"
        onSignOut={onSignOut}
        {...props}
      />
    </MemoryRouter>,
  );
  return { onSignOut };
}

describe("<StoreGate>", () => {
  it("subscription reason shows a Re-subscribe CTA to /subscribe", () => {
    renderGate({ reason: "subscription" });
    expect(screen.getByText(/subscription has ended/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /re-subscribe/i });
    expect(link).toHaveAttribute("href", "/subscribe");
  });

  it("frozen reason shows suspended copy and NO re-subscribe CTA", () => {
    renderGate({ reason: "frozen" });
    expect(screen.getByText(/account suspended/i)).toBeInTheDocument();
    expect(screen.getByText(/contact support/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /re-subscribe/i }),
    ).not.toBeInTheDocument();
  });

  it("always offers Log out, which fires onSignOut", async () => {
    const user = userEvent.setup();
    const { onSignOut } = renderGate({ reason: "frozen" });
    await user.click(screen.getByRole("button", { name: /log out/i }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it("names the store in the copy", () => {
    renderGate({ reason: "subscription", storeName: "Cambio Express" });
    expect(screen.getByText(/Cambio Express/)).toBeInTheDocument();
  });
});
