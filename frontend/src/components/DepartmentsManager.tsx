import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  createDepartment, updateDepartment, useDepartments,
  type Department,
} from "../api/dayclose";
import { ApiError } from "../lib/api";
import {
  Alert, Button, Card, EmptyState, ErrorState, Field, InfoTip, Input,
  Loading, Modal, Pill, RowActions, Section, Select, Table,
  tdStyle, thStyle, useToast,
} from "./ui";
import styles from "./DepartmentsManager.module.css";

// The store's department catalog. Departments group sales lines on a
// register close AND classify price-book items, so the catalog lives
// with the price book rather than on a close-out screen — it is
// reference data the operator maintains once, not something they
// touch every night.

// Offered as a one-click prefill on the empty catalog — never
// auto-seeded. The operator owns the catalog (HANDOFF.md §2 product
// principle): prefills are a starting point to edit, not a fixed
// vocabulary.
const STARTER_DEPARTMENTS = [
  "Grocery", "Beverages", "Snacks & Candy", "Tobacco",
  "Beer & Wine", "Deli", "Lottery", "Other",
];

export default function DepartmentsManager() {
  const [showInactive, setShowInactive] = useState(false);
  const departments = useDepartments(showInactive);
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Department | null>(null);
  const [seeding, setSeeding] = useState(false);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["dayclose"] });
  }

  async function addStarterSet() {
    setSeeding(true);
    try {
      for (const [i, name] of STARTER_DEPARTMENTS.entries()) {
        await createDepartment({ name, sort_order: (i + 1) * 10 });
      }
      refresh();
      toast({
        message:
          "Starter departments added — rename or remove any to fit your store.",
        tone: "success",
      });
    } catch (err) {
      refresh();
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not add the starter departments.",
        tone: "error",
      });
    } finally {
      setSeeding(false);
    }
  }

  async function toggleActive(d: Department) {
    try {
      await updateDepartment(d.id, { is_active: !d.is_active });
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not update the department.",
        tone: "error",
      });
    }
  }

  return (
    <Section
      title={
        <>
          Departments
          <InfoTip text="How sales are grouped — on a register close and on every price-book item. Deactivate rather than delete: historical sales keep pointing at the department they were rung under." />
        </>
      }
      actions={
        <div className={styles.actions}>
          <Button
            size="sm" tone="secondary"
            onClick={() => setShowInactive((v) => !v)}
          >
            {showInactive ? "Hide inactive" : "Show inactive"}
          </Button>
          <Button size="sm" onClick={() => setAdding(true)}>
            + Add department
          </Button>
        </div>
      }
    >
      {departments.isLoading && <Loading />}
      {departments.isError && (
        <ErrorState
          message="Could not load departments."
          onRetry={() => { void departments.refetch(); }}
        />
      )}
      {departments.data && departments.data.departments.length === 0 && (
        <EmptyState
          title="No departments yet"
          body="Start from a typical store's set and make it your own — rename, remove, or add anything — or build from scratch with &quot;+ Add department&quot;."
          cta={
            <Button size="sm" busy={seeding} disabled={seeding}
              onClick={() => { void addStarterSet(); }}
            >
              Add starter departments
            </Button>
          }
        />
      )}
      {departments.data && departments.data.departments.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                {["Department", "Parent", "Sort", "Status", "Actions"].map(
                  (h) => <th key={h} style={thStyle}>{h}</th>,
                )}
              </tr>
            </thead>
            <tbody>
              {departments.data.departments.map((d) => (
                <tr key={d.id}>
                  <td style={tdStyle}>{d.name}</td>
                  <td style={tdStyle}>{d.parent_name || "—"}</td>
                  <td style={tdStyle}>{d.sort_order}</td>
                  <td style={tdStyle}>
                    <Pill tone={d.is_active ? "accent" : "neutral"}>
                      {d.is_active ? "active" : "inactive"}
                    </Pill>
                  </td>
                  <td style={tdStyle}>
                    <RowActions
                      title={d.name}
                      actions={[
                        {
                          label: "Edit",
                          tone: "primary",
                          onClick: () => setEditing(d),
                        },
                        {
                          label: d.is_active ? "Deactivate" : "Reactivate",
                          tone: d.is_active ? "warning" : "primary",
                          onClick: () => toggleActive(d),
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
      <DepartmentModal
        open={adding || editing != null}
        existing={editing}
        departments={departments.data?.departments ?? []}
        onClose={() => { setAdding(false); setEditing(null); }}
        onDone={() => { setAdding(false); setEditing(null); refresh(); }}
      />
    </Section>
  );
}

function DepartmentModal({
  open, existing, departments, onClose, onDone,
}: {
  open: boolean;
  existing: Department | null;
  departments: Department[];
  onClose: () => void;
  onDone: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={existing ? `Edit ${existing.name}` : "Add a department"}
    >
      {open && (
        // Keyed remount resets the form per open/target — prefill
        // via initializers, no state-sync effect needed.
        <DepartmentForm
          key={existing?.id ?? "new"}
          existing={existing}
          departments={departments}
          onClose={onClose}
          onDone={onDone}
        />
      )}
    </Modal>
  );
}

function DepartmentForm({
  existing, departments, onClose, onDone,
}: {
  existing: Department | null;
  departments: Department[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(existing?.name ?? "");
  const [sortOrder, setSortOrder] = useState(
    String(existing?.sort_order ?? 0),
  );
  const [parentId, setParentId] = useState(
    existing?.parent_id != null ? String(existing.parent_id) : "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Valid parents: top-level departments other than this one
  // (sub-departments go one level deep — the server enforces it,
  // the picker just doesn't offer invalid choices).
  const parentChoices = departments.filter(
    (d) => d.parent_id == null && d.id !== existing?.id,
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name: name.trim(),
      sort_order: Number.parseInt(sortOrder, 10) || 0,
    };
    try {
      if (existing) {
        await updateDepartment(existing.id, {
          ...body,
          // 0 clears the parent link (server PATCH semantics).
          parent_id: parentId === "" ? 0 : Number(parentId),
        });
      } else {
        await createDepartment({
          ...body,
          parent_id: parentId === "" ? null : Number(parentId),
        });
      }
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className={styles.modalForm}>
      {error && <Alert tone="error">{error}</Alert>}
      <Field label="Name">
        <Input
          type="text" value={name} required maxLength={80}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field
        label={
          <>
            Sort order
            <InfoTip text="Lower numbers list first on the register-close entry form and reports." />
          </>
        }
      >
        <Input
          type="number" min={0} value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value)}
        />
      </Field>
      <Field
        label={
          <>
            Parent department (optional)
            <InfoTip text="Nest this under a top-level department to group related lines — e.g. Tobacco › Cigarettes. One level deep." />
          </>
        }
      >
        <Select
          value={parentId}
          onChange={(e) => setParentId(e.target.value)}
        >
          <option value="">None (top level)</option>
          {parentChoices.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </Select>
      </Field>
      <div className={styles.modalActions}>
        <Button tone="secondary" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" busy={busy} disabled={busy}>
          {existing ? "Save changes" : "Add department"}
        </Button>
      </div>
    </form>
  );
}
