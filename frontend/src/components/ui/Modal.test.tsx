import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Modal, ConfirmDialog } from "./Modal";

describe("<Modal>", () => {
  it("renders nothing when open=false", () => {
    render(
      <Modal open={false} onClose={() => {}} title="Hidden">
        body
      </Modal>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders a dialog with the title + body when open=true", () => {
    render(
      <Modal open onClose={() => {}} title="Hello">
        Body content
      </Modal>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();
  });

  it("aria-labelledby wires the dialog to the title node id", () => {
    render(
      <Modal open onClose={() => {}} title="Hello">x</Modal>,
    );
    const dialog = screen.getByRole("dialog");
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    expect(
      document.getElementById(labelledBy as string)?.textContent,
    ).toBe("Hello");
  });

  it("fires onClose on Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Closable">body</Modal>,
    );
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("does NOT fire onClose on Escape when disabled=true (busy save)", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Busy" disabled>body</Modal>,
    );
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("traps Tab focus inside the dialog and hides the page behind it", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <>
        <button>Outside</button>
        <Modal open onClose={() => {}} title="Trap test">
          <button>First</button>
          <button>Second</button>
        </Modal>
      </>,
    );
    // Radix marks everything behind the overlay aria-hidden —
    // the page is gone from the accessibility tree while the
    // dialog is open.
    const outside = container.querySelector("button");
    expect(outside).toHaveTextContent("Outside");
    expect(outside?.closest("[aria-hidden='true']")).not.toBeNull();
    // Tab repeatedly — focus must cycle through the dialog's
    // controls and never land on the button behind the overlay.
    for (let i = 0; i < 5; i++) {
      await user.tab();
      expect(outside).not.toHaveFocus();
      const dialog = screen.getByRole("dialog");
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });

  it("renders the actions row when actions prop is provided", () => {
    render(
      <Modal
        open onClose={() => {}} title="With actions"
        actions={<button>Save</button>}
      >
        body
      </Modal>,
    );
    expect(screen.getByRole("button", { name: "Save" }))
      .toBeInTheDocument();
  });
});

describe("<ConfirmDialog>", () => {
  it("renders title + message + Cancel + Confirm buttons when open", () => {
    render(
      <ConfirmDialog
        open
        title="Delete?"
        message="This cannot be undone."
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByText("Delete?")).toBeInTheDocument();
    expect(screen.getByText("This cannot be undone.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" }))
      .toBeInTheDocument();
  });

  it("fires onConfirm when Confirm clicked", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Delete?"
        message="x"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("fires onCancel when Cancel clicked", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Delete?"
        message="x"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("uses custom confirmLabel / cancelLabel when provided", () => {
    render(
      <ConfirmDialog
        open
        title="Disconnect bank?"
        message="x"
        confirmLabel="Disconnect"
        cancelLabel="Keep"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Disconnect" }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep" }))
      .toBeInTheDocument();
  });

  it("disables both buttons + blocks Escape while busy=true", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open busy
        title="Saving"
        message="x"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });
});
