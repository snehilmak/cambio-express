import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ToastProvider, useToast } from "./Toast";

// Tiny inline trigger so each test can push a toast with custom
// input.  Avoids re-declaring it per case.
function Trigger({ message, duration }: { message: string; duration?: number }) {
  const toast = useToast();
  return (
    <button onClick={() => toast({ message, duration })}>push</button>
  );
}

describe("<ToastProvider> + useToast", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a toast when the hook pushes one", async () => {
    const user = userEvent.setup({
      advanceTimers: vi.advanceTimersByTime.bind(vi),
    });
    render(
      <ToastProvider>
        <Trigger message="Profile saved." />
      </ToastProvider>,
    );
    await user.click(screen.getByText("push"));
    expect(screen.getByText("Profile saved.")).toBeInTheDocument();
  });

  it("auto-dismisses after the duration elapses", async () => {
    const user = userEvent.setup({
      advanceTimers: vi.advanceTimersByTime.bind(vi),
    });
    render(
      <ToastProvider>
        <Trigger message="Goodbye." duration={1000} />
      </ToastProvider>,
    );
    await user.click(screen.getByText("push"));
    expect(screen.getByText("Goodbye.")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1100);
    });
    await waitFor(() => {
      expect(screen.queryByText("Goodbye.")).toBeNull();
    });
  });

  it("does NOT auto-dismiss when duration is 0 (sticky)", async () => {
    const user = userEvent.setup({
      advanceTimers: vi.advanceTimersByTime.bind(vi),
    });
    render(
      <ToastProvider>
        <Trigger message="Sticky." duration={0} />
      </ToastProvider>,
    );
    await user.click(screen.getByText("push"));
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.getByText("Sticky.")).toBeInTheDocument();
  });

  it("dismisses on × button click", async () => {
    const user = userEvent.setup({
      advanceTimers: vi.advanceTimersByTime.bind(vi),
    });
    render(
      <ToastProvider>
        <Trigger message="Click me away." duration={0} />
      </ToastProvider>,
    );
    await user.click(screen.getByText("push"));
    await user.click(screen.getByLabelText("Dismiss"));
    await waitFor(() => {
      expect(screen.queryByText("Click me away.")).toBeNull();
    });
  });

  it("throws if useToast is called outside ToastProvider", () => {
    function Orphan() {
      useToast();
      return null;
    }
    // Silence React's expected-render-error noise for this case.
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Orphan />)).toThrow(
      /requires <ToastProvider>/,
    );
    err.mockRestore();
  });
});
