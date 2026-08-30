import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  createDepartment, deleteRegisterClose, updateDepartment,
  upsertRegisterClose, useDayClose, useDepartments,
  type Department, type RegisterClose,
} from "../api/dayclose";
import { ApiError } from "../lib/api";
import { fmtMoney2 } from "../lib/formatters";
import {
  Alert, Breadcrumbs, Button, ButtonLink, Card, DateInput, EmptyState,
  ErrorState, Field, InfoTip, Input, KpiCard, KpiGrid, Loading, Modal,
  PageHeader, PageShell, Pill, RowActions, Section, Select, TabsBar,
  TabsButton, Table, Textarea, tdStyle, thStyle, useToast,
} from "../components/ui";
import styles from "./DayClose.module.css";

// Offered as a one-click prefill on the empty Departments tab —
// never auto-seeded. The operator owns the catalog (HANDOFF.md §2
// product principle): prefills are a starting point to edit, not
// a fixed vocabulary.
const STARTER_DEPARTMENTS = [
  "Grocery", "Beverages", "Snacks & Candy", "Tobacco",
  "Beer & Wine", "Deli", "Lottery", "Other",
];

function localToday(): string {
  // en-CA formats as YYYY-MM-DD in the browser's local timezone —
  // the store closes its day at ITS closing time, not UTC's.
  return new Date().toLocaleDateString("en-CA");
}

export default function DayClose() {
  const [tab, setTab] = useState<"day" | "departments">("day");
  return (
    <PageShell maxWidth="64rem">
      <Breadcrumbs crumbs={[{ label: "Day close" }]} />
      <PageHeader
        title={
          <>
            Day close
            <InfoTip text="Key each register or shift Z-report — sales, tax, and tender totals plus the department breakdown. Drawer over/short computes from the counted cash." />
          </>
        }
        subtitle="Register totals and department sales."
        actions={
          <ButtonLink to="/pos-import" size="sm" tone="secondary">
            Import from register
          </ButtonLink>
        }
      />
      <TabsBar>
        <TabsButton active={tab === "day"} onClick={() => setTab("day")}>
          Day close
        </TabsButton>
        <TabsButton
          active={tab === "departments"}
          onClick={() => setTab("departments")}
        >
          Departments
        </TabsButton>
      </TabsBar>
      {tab === "day" && <DayTab />}
      {tab === "departments" && <DepartmentsTab />}
    </PageShell>
  );
}

// ── Day tab ──────────────────────────────────────────────────

function DayTab() {
  const [day, setDay] = useState(localToday());
  const summary = useDayClose(day);
  const departments = useDepartments();
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<RegisterClose | null>(null);
  const [adding, setAdding] = useState(false);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["dayclose", "day"] });
  }

  async function remove(close: RegisterClose) {
    try {
      await deleteRegisterClose(close.id);
      refresh();
      toast({ message: "Register close removed.", tone: "success" });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not remove the close.",
        tone: "error",
      });
    }
  }

  const data = summary.data;
  return (
    <Section
      title="Register closes"
      actions={
        <div className={styles.departmentsActions}>
          <DateInput
            aria-label="Close date"
            value={day}
            onChange={(e) => setDay(e.target.value)}
          />
          <Button size="sm" onClick={() => setAdding(true)}>
            + Add close
          </Button>
        </div>
      }
    >
      {summary.isLoading && <Loading />}
      {summary.isError && (
        <ErrorState
          message="Could not load the day."
          onRetry={() => { void summary.refetch(); }}
        />
      )}
      {data && data.closes.length === 0 && (
        <EmptyState
          title="No closes for this day"
          body='Click "+ Add close" to key the first Z-report.'
        />
      )}
      {data && data.closes.length > 0 && (
        <>
          <KpiGrid>
            <KpiCard label="Gross sales" value={fmtMoney2(data.gross_sales)} />
            <KpiCard label="Sales tax" value={fmtMoney2(data.sales_tax)} />
            <KpiCard
              label="Drawer over / short"
              value={
                data.over_short == null ? "—" : fmtMoney2(data.over_short)
              }
              tone={
                data.over_short == null || data.over_short === 0
                  ? "positive" : "negative"
              }
            />
            <KpiCard
              label="Uncounted drawers"
              value={String(data.uncounted_drawers)}
              tone={data.uncounted_drawers > 0 ? "negative" : "positive"}
            />
          </KpiGrid>
          <Card>
            <div style={{ overflowX: "auto" }}>
              <Table>
                <thead>
                  <tr>
                    {["Register", "Gross", "Tax", "Cash", "Card", "Other",
                      "Counted", "Over/short", "Actions"].map((h) => (
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.closes.map((c) => (
                    <tr
                      key={c.id}
                      className={
                        c.cash_counted == null ? styles.uncountedRow : ""
                      }
                    >
                      <td style={tdStyle}>
                        {c.register_label}
                        {c.shift_label ? ` / ${c.shift_label}` : ""}
                      </td>
                      <td style={tdStyle}>{fmtMoney2(c.gross_sales)}</td>
                      <td style={tdStyle}>{fmtMoney2(c.sales_tax)}</td>
                      <td style={tdStyle}>{fmtMoney2(c.cash_total)}</td>
                      <td style={tdStyle}>{fmtMoney2(c.card_total)}</td>
                      <td style={tdStyle}>{fmtMoney2(c.other_total)}</td>
                      <td style={tdStyle}>
                        {c.cash_counted == null
                          ? "—" : fmtMoney2(c.cash_counted)}
                      </td>
                      <td style={tdStyle}>
                        {c.over_short == null
                          ? "—" : fmtMoney2(c.over_short)}
                      </td>
                      <td style={tdStyle}>
                        <RowActions
                          title={c.register_label}
                          actions={[
                            {
                              label: "Edit",
                              tone: "primary",
                              onClick: () => setEditing(c),
                            },
                            {
                              label: "Delete",
                              tone: "warning",
                              onClick: () => remove(c),
                            },
                          ]}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          </Card>
          {data.department_totals.length > 0 && (
            <Card>
              <div style={{ overflowX: "auto" }}>
                <Table>
                  <thead>
                    <tr>
                      <th style={thStyle}>Department</th>
                      <th style={thStyle}>Sales</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.department_totals.map((t) => (
                      <tr key={t.department_id}>
                        <td style={tdStyle}>{t.department_name}</td>
                        <td style={tdStyle}>{fmtMoney2(t.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            </Card>
          )}
        </>
      )}
      <CloseModal
        open={adding || editing != null}
        day={day}
        existing={editing}
        departments={departments.data?.departments ?? []}
        onClose={() => { setAdding(false); setEditing(null); }}
        onDone={() => { setAdding(false); setEditing(null); refresh(); }}
      />
    </Section>
  );
}

// ── Close modal (add / edit one register-shift Z-report) ─────

function CloseModal({
  open, day, existing, departments, onClose, onDone,
}: {
  open: boolean;
  day: string;
  existing: RegisterClose | null;
  departments: Department[];
  onClose: () => void;
  onDone: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        <>
          {existing ? "Edit register close" : "Add register close"}
          <InfoTip text="Key the Z-report as printed. Re-saving the same register and shift replaces the earlier entry. Leave counted cash blank until the drawer is actually counted — blank is 'not counted yet', not $0." />
        </>
      }
    >
      {open && (
        // Keyed remount resets the form per open/target — prefill
        // via initializers, no state-sync effect needed.
        <CloseForm
          key={existing?.id ?? "new"}
          day={day}
          existing={existing}
          departments={departments}
          onClose={onClose}
          onDone={onDone}
        />
      )}
    </Modal>
  );
}

function CloseForm({
  day, existing, departments, onClose, onDone,
}: {
  day: string;
  existing: RegisterClose | null;
  departments: Department[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [registerLabel, setRegisterLabel] = useState(
    existing?.register_label ?? "Register 1",
  );
  const [shiftLabel, setShiftLabel] = useState(existing?.shift_label ?? "");
  const [gross, setGross] = useState(
    existing ? String(existing.gross_sales) : "",
  );
  const [tax, setTax] = useState(existing ? String(existing.sales_tax) : "");
  const [cash, setCash] = useState(
    existing ? String(existing.cash_total) : "",
  );
  const [card, setCard] = useState(
    existing ? String(existing.card_total) : "",
  );
  const [other, setOther] = useState(
    existing ? String(existing.other_total) : "",
  );
  const [counted, setCounted] = useState(
    existing?.cash_counted != null ? String(existing.cash_counted) : "",
  );
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [deptAmounts, setDeptAmounts] = useState<Record<number, string>>(
    () => {
      const amounts: Record<number, string> = {};
      for (const line of existing?.department_sales ?? []) {
        amounts[line.department_id] = String(line.amount);
      }
      return amounts;
    },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const lines = departments
      .map((d) => ({
        department_id: d.id,
        amount: Number.parseFloat(deptAmounts[d.id] ?? "") || 0,
      }))
      .filter((l) => l.amount > 0);
    try {
      await upsertRegisterClose(day, {
        register_label: registerLabel.trim(),
        shift_label: shiftLabel.trim(),
        gross_sales: Number.parseFloat(gross) || 0,
        sales_tax: Number.parseFloat(tax) || 0,
        cash_total: Number.parseFloat(cash) || 0,
        card_total: Number.parseFloat(card) || 0,
        other_total: Number.parseFloat(other) || 0,
        cash_counted:
          counted.trim() === "" ? null : Number.parseFloat(counted) || 0,
        notes: notes.trim(),
        department_sales: lines,
      });
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
        <div className={styles.moneyGrid}>
          <Field label="Register">
            <Input
              type="text" value={registerLabel} required maxLength={40}
              disabled={existing != null}
              onChange={(e) => setRegisterLabel(e.target.value)}
            />
          </Field>
          <Field label="Shift (optional)">
            <Input
              type="text" value={shiftLabel} maxLength={40}
              placeholder="e.g. Morning"
              disabled={existing != null}
              onChange={(e) => setShiftLabel(e.target.value)}
            />
          </Field>
          <Field label="Gross sales">
            <Input
              type="number" min={0} step="0.01" value={gross} required
              onChange={(e) => setGross(e.target.value)}
            />
          </Field>
          <Field label="Sales tax">
            <Input
              type="number" min={0} step="0.01" value={tax}
              onChange={(e) => setTax(e.target.value)}
            />
          </Field>
          <Field label="Cash tender">
            <Input
              type="number" min={0} step="0.01" value={cash}
              onChange={(e) => setCash(e.target.value)}
            />
          </Field>
          <Field label="Card tender">
            <Input
              type="number" min={0} step="0.01" value={card}
              onChange={(e) => setCard(e.target.value)}
            />
          </Field>
          <Field label="Other tender">
            <Input
              type="number" min={0} step="0.01" value={other}
              onChange={(e) => setOther(e.target.value)}
            />
          </Field>
          <Field label="Counted drawer cash">
            <Input
              type="number" min={0} step="0.01" value={counted}
              placeholder="Blank = not counted"
              onChange={(e) => setCounted(e.target.value)}
            />
          </Field>
        </div>
        {departments.length > 0 && (
          <Field label="Department sales">
            <div className={styles.modalForm}>
              {departments.map((d) => (
                <div key={d.id} className={styles.deptRow}>
                  <span className={styles.deptName}>{d.name}</span>
                  <Input
                    type="number" min={0} step="0.01"
                    className={styles.deptAmount}
                    aria-label={`${d.name} sales`}
                    value={deptAmounts[d.id] ?? ""}
                    onChange={(e) =>
                      setDeptAmounts((prev) => ({
                        ...prev, [d.id]: e.target.value,
                      }))
                    }
                  />
                </div>
              ))}
            </div>
          </Field>
        )}
        <Field label="Notes (optional)">
          <Textarea
            value={notes} maxLength={500} rows={2}
            onChange={(e) => setNotes(e.target.value)}
          />
        </Field>
        <div className={styles.modalActions}>
          <Button tone="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={busy}>
            {existing ? "Save changes" : "Add close"}
          </Button>
        </div>
    </form>
  );
}

// ── Departments tab ──────────────────────────────────────────

function DepartmentsTab() {
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
      title="Departments"
      actions={
        <div className={styles.departmentsActions}>
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
          <div style={{ overflowX: "auto" }}>
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
          </div>
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
              <InfoTip text="Lower numbers list first on the day-close entry form and reports." />
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
