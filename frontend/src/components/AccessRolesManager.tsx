import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  createAccessRole, deleteAccessRole, fetchRoleMembers,
  updateAccessRole, useAccessRoles,
  type AccessRole, type PermMatrix, type RoleMember,
} from "../api/roles";
import { ApiError } from "../lib/api";
import {
  Alert, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field,
  InfoTip, Input, Loading, Modal, Pill, RowActions, Section, Table,
  tdStyle, thStyle, useToast,
} from "./ui";
import { PermissionMatrixTable } from "./PermissionMatrixTable";
import styles from "./AccessRolesManager.module.css";

// Saved access roles (R-3). Editing one changes what its members
// can do RIGHT NOW — so the destructive-feeling part of this UI is
// the save, not the delete, and the confirmation names the people
// it will affect. "Changes access for 6 people" without saying who
// is not a confirmation.

function emptyMatrix(resources: string[], actions: string[]): PermMatrix {
  const out: PermMatrix = {};
  for (const r of resources) {
    out[r] = {};
    for (const a of actions) out[r][a] = false;
  }
  return out;
}

export default function AccessRolesManager() {
  const roles = useAccessRoles();
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<AccessRole | null>(null);
  const [adding, setAdding] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<AccessRole | null>(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["admin", "roles"] });
  }

  async function remove(role: AccessRole) {
    setBusy(true);
    try {
      const res = await deleteAccessRole(role.id);
      refresh();
      toast({
        message: res.detached.length
          ? `Deleted "${res.deleted}". ${res.detached.length} `
            + "person's access is unchanged."
          : `Deleted "${res.deleted}".`,
        tone: "success",
      });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not delete the role.",
        tone: "error",
      });
    } finally {
      setBusy(false);
      setConfirmDelete(null);
    }
  }

  const data = roles.data;
  return (
    <Section
      title={
        <>
          Access roles
          <InfoTip text="A saved set of permissions you can give to more than one person. Editing a role changes what everyone in it can do immediately — you'll see who before it saves." />
        </>
      }
      actions={
        <Button size="sm" onClick={() => setAdding(true)}>
          + New role
        </Button>
      }
    >
      {roles.isLoading && <Loading />}
      {roles.isError && (
        <ErrorState
          message="Could not load access roles."
          onRetry={() => { void roles.refetch(); }}
        />
      )}
      {data && data.roles.length === 0 && (
        <EmptyState
          title="No saved roles yet"
          body="Set someone's access the way you want it, then save it as a role — the next hire with the same job gets it in one click instead of twenty checkboxes."
        />
      )}
      {data && data.roles.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                {["Role", "People", "Areas", "Actions"].map((h) => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.roles.map((r) => {
                const areas = data.resources.filter((res) =>
                  data.actions.some((a) => r.matrix[res]?.[a]),
                ).length;
                return (
                  <tr key={r.id}>
                    <td style={tdStyle}>{r.name}</td>
                    <td style={tdStyle}>
                      <Pill tone={r.member_count > 0 ? "accent" : "neutral"}>
                        {r.member_count === 1
                          ? "1 person" : `${r.member_count} people`}
                      </Pill>
                    </td>
                    <td style={tdStyle}>
                      {areas} of {data.resources.length}
                    </td>
                    <td style={tdStyle}>
                      <RowActions
                        title={r.name}
                        actions={[
                          {
                            label: "Edit",
                            tone: "primary",
                            onClick: () => setEditing(r),
                          },
                          {
                            label: "Delete",
                            tone: "warning",
                            onClick: () => setConfirmDelete(r),
                          },
                        ]}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </Card>
      )}

      <Modal
        open={adding || editing != null}
        onClose={() => { setAdding(false); setEditing(null); }}
        title={editing ? `Edit ${editing.name}` : "New access role"}
      >
        {(adding || editing != null) && data && (
          <RoleForm
            key={editing?.id ?? "new"}
            existing={editing}
            resources={data.resources}
            actions={data.actions}
            onClose={() => { setAdding(false); setEditing(null); }}
            onDone={() => { setAdding(false); setEditing(null); refresh(); }}
          />
        )}
      </Modal>

      <ConfirmDialog
        open={confirmDelete != null}
        title={`Delete "${confirmDelete?.name ?? ""}"`}
        message={
          (confirmDelete?.member_count ?? 0) > 0
            ? `${confirmDelete?.member_count} person/people are in this role. `
              + "Deleting it does NOT change what they can do — they keep "
              + "exactly the access they have now, it just stops being "
              + "tracked as a role."
            : "This role has no members."
        }
        confirmLabel="Delete role"
        busy={busy}
        onConfirm={() => {
          if (confirmDelete) void remove(confirmDelete);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </Section>
  );
}

function RoleForm({
  existing, resources, actions, onClose, onDone,
}: {
  existing: AccessRole | null;
  resources: string[];
  actions: string[];
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(existing?.name ?? "");
  const [matrix, setMatrix] = useState<PermMatrix>(() =>
    existing
      ? structuredClone(existing.matrix)
      : emptyMatrix(resources, actions),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Non-null once we've asked the server who this edit would hit.
  const [pending, setPending] = useState<RoleMember[] | null>(null);

  function toggle(resource: string, action: string) {
    setMatrix((m) => {
      const next = structuredClone(m);
      next[resource] = next[resource] ?? {};
      next[resource][action] = !next[resource][action];
      return next;
    });
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (existing) {
        const res = await updateAccessRole(existing.id, { name, matrix });
        const n = res.affected_members?.length ?? 0;
        toast({
          message: n
            ? `Saved. Access updated for ${n} `
              + `${n === 1 ? "person" : "people"}.`
            : "Saved.",
          tone: "success",
        });
      } else {
        await createAccessRole({ name, matrix });
        toast({ message: "Role created.", tone: "success" });
      }
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
      setPending(null);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    // A new role has no members, and neither does an empty one —
    // go straight through rather than confirming nothing.
    if (!existing || existing.member_count === 0) {
      void save();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetchRoleMembers(existing.id);
      setPending(res.members);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message : "Could not check who this affects.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={onSubmit} className={styles.form}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Role name" hint="What this job is called in your store — “Shift lead”, “Bookkeeper”.">
          <Input
            type="text" value={name} required maxLength={60}
            placeholder="Shift lead"
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        {existing && existing.member_count > 0 && (
          <Alert tone="info">
            {existing.member_count === 1
              ? "1 person has this role."
              : `${existing.member_count} people have this role.`}
            {" "}Saving changes what they can do right away.
          </Alert>
        )}
        <Field label="Permissions">
          <PermissionMatrixTable
            resources={resources}
            actions={actions}
            checked={(r, a) => matrix[r]?.[a] ?? false}
            onToggle={toggle}
            disabled={busy}
            resourceHeader="Area"
          />
        </Field>
        <div className={styles.actions}>
          <Button tone="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={busy}>
            {existing ? "Save role" : "Create role"}
          </Button>
        </div>
      </form>

      <ConfirmDialog
        open={pending != null}
        title="This changes people's access"
        message={
          pending && pending.length
            ? `Saving updates access for ${pending.length} `
              + `${pending.length === 1 ? "person" : "people"}: `
              + `${pending.map((m) => m.name).join(", ")}. `
              + "They'll be signed out so the change takes effect."
            : "Saving updates this role."
        }
        confirmLabel="Save and update them"
        busy={busy}
        onConfirm={() => { void save(); }}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
