import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";

import AccessRolesManager from "./AccessRolesManager";
import { ToastProvider } from "./ui";

// Editing a role changes what its members can do RIGHT NOW, so the
// part worth testing is the confirmation: it must NAME the people
// it affects before the save goes through, and it must not nag
// when a role has nobody in it.

const listResponse = {
  resources: ["transfers", "monthly"],
  actions: ["create", "read", "update", "delete"],
  roles: [
    {
      id: 1,
      name: "Shift lead",
      member_count: 2,
      matrix: {
        transfers: {
          create: false, read: true, update: false, delete: false,
        },
        monthly: {
          create: false, read: false, update: false, delete: false,
        },
      },
      updated_at: null,
    },
    {
      id: 2,
      name: "Nobody's role",
      member_count: 0,
      matrix: {
        transfers: {
          create: false, read: false, update: false, delete: false,
        },
        monthly: {
          create: false, read: false, update: false, delete: false,
        },
      },
      updated_at: null,
    },
  ],
};

const fetchRoleMembers = vi.fn();
const updateAccessRole = vi.fn();

vi.mock("../api/roles", () => ({
  useAccessRoles: () => ({
    data: listResponse, isLoading: false, isError: false,
  }),
  fetchRoleMembers: (...args: unknown[]) => fetchRoleMembers(...args),
  updateAccessRole: (...args: unknown[]) => updateAccessRole(...args),
  createAccessRole: vi.fn(),
  deleteAccessRole: vi.fn(),
  assignAccessRole: vi.fn(),
}));

function renderManager() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <AccessRolesManager />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchRoleMembers.mockReset();
  updateAccessRole.mockReset();
  fetchRoleMembers.mockResolvedValue({
    role_id: 1,
    name: "Shift lead",
    members: [
      { id: 10, name: "Amber" },
      { id: 11, name: "Ben" },
    ],
  });
  updateAccessRole.mockResolvedValue({
    ...listResponse.roles[0],
    affected_members: [
      { id: 10, name: "Amber" },
      { id: 11, name: "Ben" },
    ],
  });
});

describe("AccessRolesManager", () => {
  it("lists roles with how many people are in each", () => {
    renderManager();
    expect(screen.getByText("Shift lead")).toBeInTheDocument();
    expect(screen.getByText("2 people")).toBeInTheDocument();
    expect(screen.getByText("0 people")).toBeInTheDocument();
  });

  it("names the affected people before saving an edit", async () => {
    const user = userEvent.setup();
    renderManager();
    await user.click(screen.getAllByText("Edit")[0]);
    await user.click(await screen.findByText("Save role"));

    // The confirmation must say WHO — a bare count is not a
    // confirmation.
    const dialog = await screen.findByText(/Amber, Ben/);
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText(/signed out/)).toBeInTheDocument();
    // …and nothing is saved until it is confirmed.
    expect(updateAccessRole).not.toHaveBeenCalled();

    await user.click(screen.getByText("Save and update them"));
    await waitFor(() => expect(updateAccessRole).toHaveBeenCalledTimes(1));
  });

  it("does not ask for confirmation on a role with no members", async () => {
    const user = userEvent.setup();
    renderManager();
    await user.click(screen.getAllByText("Edit")[1]);
    await user.click(await screen.findByText("Save role"));

    await waitFor(() => expect(updateAccessRole).toHaveBeenCalledTimes(1));
    expect(fetchRoleMembers).not.toHaveBeenCalled();
  });

  it("warns inside the form that a save reaches everyone", async () => {
    const user = userEvent.setup();
    renderManager();
    await user.click(screen.getAllByText("Edit")[0]);
    expect(
      await screen.findByText(/2 people have this role/),
    ).toBeInTheDocument();
  });
});
