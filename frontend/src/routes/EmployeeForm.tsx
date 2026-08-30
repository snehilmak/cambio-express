import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  createEmployee, linkEmployeeLogin, unlinkEmployeeLogin,
  updateEmployee, useEmployees,
  type EmployeeCreateBody, type EmployeeUpdateBody,
} from "../api/employees";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Breadcrumbs, Button, ButtonLink, Card, Checkbox,
  ConfirmDialog, DateInput, Empty, ErrorState, Field, Input, Loading,
  PageHeader, PageShell, Pill, Section, Select, useToast,
} from "../components/ui";
import { useUnsavedGuard } from "../lib/useUnsavedGuard";

// /app/employees/new + /app/employees/:id/edit — the person form
// of the unified Employees hub (E-2). Sections: Basic, Payroll,
// Contact, Login. The Login section links/unlinks a login
// account; editing credentials + role + custom access stays on
// the dedicated login form (/admin/users/:uid/edit) so the R-2
// access UI has exactly one home.

const SCHEDULES = [
  { value: "", label: "Not set" },
  { value: "weekly", label: "Weekly" },
  { value: "biweekly", label: "Biweekly" },
  { value: "semimonthly", label: "Semimonthly" },
  { value: "monthly", label: "Monthly" },
];

interface Draft {
  name: string;
  is_active: boolean;
  hourly_rate: string;
  hired_on: string;
  date_of_birth: string;
  email: string;
  phone: string;
  address_line1: string;
  address_line2: string;
  payroll_schedule: string;
}

const BLANK: Draft = {
  name: "", is_active: true, hourly_rate: "",
  hired_on: "", date_of_birth: "", email: "", phone: "",
  address_line1: "", address_line2: "", payroll_schedule: "",
};

export default function EmployeeForm() {
  const { id: idStr } = useParams();
  const empId = idStr ? Number(idStr) : null;
  const isEdit = empId != null;

  const identity = getCurrentIdentity();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const list = useEmployees();

  const existing = useMemo(
    () => list.data?.rows.find((r) => r.id === empId) ?? null,
    [list.data, empId],
  );
  const loginOnly = list.data?.login_only ?? [];

  const [draft, setDraft] = useState<Draft>(BLANK);
  const [baseline, setBaseline] = useState<Draft>(BLANK);
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [linkPick, setLinkPick] = useState<string>("");
  const [confirmUnlink, setConfirmUnlink] = useState(false);

  useEffect(() => {
    if (!isEdit || !existing) return;
    const hydrated: Draft = {
      name: existing.name,
      is_active: existing.is_active,
      hourly_rate: existing.hourly_rate > 0
        ? String(existing.hourly_rate) : "",
      hired_on: existing.hired_on ?? "",
      date_of_birth: existing.date_of_birth ?? "",
      email: existing.email,
      phone: existing.phone,
      address_line1: existing.address_line1,
      address_line2: existing.address_line2,
      payroll_schedule: existing.payroll_schedule,
    };
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable draft + dirty baseline from the fetched employee row
    setDraft(hydrated);
    setBaseline(hydrated);
  }, [isEdit, existing]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  const guard = useUnsavedGuard(isDirty && !busy, {
    message: "You have unsaved edits on this employee. Leave without saving?",
  });

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["employees"] });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setServerError(null);
    try {
      if (isEdit) {
        const body: EmployeeUpdateBody = {
          name: draft.name,
          is_active: draft.is_active,
          hourly_rate: Number(draft.hourly_rate) || 0,
          email: draft.email,
          phone: draft.phone,
          address_line1: draft.address_line1,
          address_line2: draft.address_line2,
          payroll_schedule: draft.payroll_schedule,
        };
        if (draft.hired_on) body.hired_on = draft.hired_on;
        else body.clear_hired_on = true;
        if (draft.date_of_birth) body.date_of_birth = draft.date_of_birth;
        else body.clear_date_of_birth = true;
        await updateEmployee(empId, body);
        toast({ message: "Employee updated.", tone: "success" });
      } else {
        const body: EmployeeCreateBody = {
          name: draft.name.trim(),
          hourly_rate: Number(draft.hourly_rate) || 0,
          email: draft.email,
          phone: draft.phone,
          address_line1: draft.address_line1,
          address_line2: draft.address_line2,
          payroll_schedule: draft.payroll_schedule,
        };
        if (draft.hired_on) body.hired_on = draft.hired_on;
        if (draft.date_of_birth) body.date_of_birth = draft.date_of_birth;
        await createEmployee(body);
        toast({ message: "Employee created.", tone: "success" });
      }
      refresh();
      navigate("/employees");
    } catch (err) {
      setServerError(
        err instanceof ApiError
          ? err.message : "Could not save the employee.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onLink() {
    if (!isEdit || !linkPick) return;
    setBusy(true);
    try {
      await linkEmployeeLogin(empId, Number(linkPick));
      toast({ message: "Login linked.", tone: "success" });
      setLinkPick("");
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not link the login.",
        tone: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  async function onUnlink() {
    if (!isEdit) return;
    setBusy(true);
    try {
      await unlinkEmployeeLogin(empId);
      toast({ message: "Login unlinked.", tone: "success" });
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not unlink the login.",
        tone: "error",
      });
    } finally {
      setBusy(false);
      setConfirmUnlink(false);
    }
  }

  if (
    !identity
    || (identity.role !== "admin" && identity.role !== "owner")
  ) {
    return (
      <PageShell maxWidth="44rem">
        <PageHeader title="Employees" />
        <Empty>You need a store-admin sign-in to manage employees.</Empty>
      </PageShell>
    );
  }

  if (isEdit && list.isLoading) {
    return (
      <PageShell maxWidth="44rem">
        <PageHeader title="Edit Employee" />
        <Loading />
      </PageShell>
    );
  }
  if (isEdit && (list.isError || (list.data && !existing))) {
    return (
      <PageShell maxWidth="44rem">
        <PageHeader title="Edit Employee" />
        <ErrorState
          message="Couldn't load this employee."
          onRetry={() => { void list.refetch(); }}
        />
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="44rem">
      <Breadcrumbs crumbs={[
        { label: "Employees", to: "/employees" },
        { label: isEdit ? "Edit Employee" : "Add Employee" },
      ]} />
      <PageHeader title={isEdit ? "Edit Employee" : "Add Employee"} />

      {serverError && <Alert tone="error">{serverError}</Alert>}

      <form onSubmit={onSubmit} className="ds-form">
        <Card>
          <Section title="Basic info">
            <Field label="Full name *">
              <Input
                type="text" maxLength={120} required
                value={draft.name}
                onChange={(e) => set("name", e.target.value)}
                disabled={busy}
              />
            </Field>
            {isEdit && (
              <Checkbox
                checked={draft.is_active}
                onChange={(v) => set("is_active", v)}
                disabled={busy}
              >
                Employee is active
              </Checkbox>
            )}
          </Section>
        </Card>

        <Card>
          <Section title="Payroll">
            <Field
              label="Hourly rate"
              hint="Used by the time-clock payroll rollup and paystubs."
            >
              <Input
                type="number" min={0} step="0.01"
                value={draft.hourly_rate}
                onChange={(e) => set("hourly_rate", e.target.value)}
                disabled={busy}
              />
            </Field>
            <Field label="Hired on">
              <DateInput
                value={draft.hired_on}
                onChange={(e) => set("hired_on", e.target.value)}
                disabled={busy}
              />
            </Field>
            <Field label="Payroll schedule">
              <Select
                value={draft.payroll_schedule}
                onChange={(e) => set("payroll_schedule", e.target.value)}
                disabled={busy}
              >
                {SCHEDULES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="Date of birth">
              <DateInput
                value={draft.date_of_birth}
                onChange={(e) => set("date_of_birth", e.target.value)}
                disabled={busy}
              />
            </Field>
          </Section>
        </Card>

        <Card>
          <Section title="Contact">
            <Field label="Email">
              <Input
                type="email" maxLength={255}
                value={draft.email}
                onChange={(e) => set("email", e.target.value)}
                disabled={busy}
              />
            </Field>
            <Field label="Phone">
              <Input
                type="tel" maxLength={40}
                value={draft.phone}
                onChange={(e) => set("phone", e.target.value)}
                disabled={busy}
              />
            </Field>
            <Field label="Address line 1">
              <Input
                type="text" maxLength={255}
                value={draft.address_line1}
                onChange={(e) => set("address_line1", e.target.value)}
                disabled={busy}
              />
            </Field>
            <Field label="Address line 2">
              <Input
                type="text" maxLength={255}
                value={draft.address_line2}
                onChange={(e) => set("address_line2", e.target.value)}
                disabled={busy}
              />
            </Field>
          </Section>
        </Card>

        {isEdit && (
          <Card>
            <Section title="Login">
              {existing?.login ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <div>
                    <strong>{existing.login.username}</strong>{" "}
                    <Pill tone={existing.login.role === "admin" ? "accent" : "neutral"}>
                      {existing.login.role === "admin" ? "Super Admin" : "Employee"}
                    </Pill>{" "}
                    <Pill tone={existing.login.is_active ? "accent" : "neutral"}>
                      {existing.login.is_active ? "Active" : "Inactive"}
                    </Pill>
                    {existing.login.has_custom_permissions && (
                      <>
                        {" "}
                        <Pill tone="neutral">Custom access</Pill>
                      </>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
                    <ButtonLink
                      to={`/admin/users/${existing.login.user_id}/edit`}
                      tone="secondary" size="sm"
                    >
                      Edit login &amp; access
                    </ButtonLink>
                    <Button
                      type="button" tone="secondary" size="sm"
                      onClick={() => setConfirmUnlink(true)}
                      disabled={busy}
                    >
                      Unlink login
                    </Button>
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <p style={{ margin: 0 }}>
                    No login attached — this person appears in
                    attribution dropdowns and the time clock but
                    can't sign in.
                  </p>
                  {loginOnly.length > 0 && (
                    <Field label="Link an existing login">
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <Select
                          value={linkPick}
                          onChange={(e) => setLinkPick(e.target.value)}
                          disabled={busy}
                        >
                          <option value="">— Select —</option>
                          {loginOnly.map((u) => (
                            <option key={u.user_id} value={u.user_id}>
                              {u.username}
                              {u.full_name ? ` (${u.full_name})` : ""}
                            </option>
                          ))}
                        </Select>
                        <Button
                          type="button" tone="secondary" size="sm"
                          onClick={() => { void onLink(); }}
                          disabled={busy || !linkPick}
                        >
                          Link
                        </Button>
                      </div>
                    </Field>
                  )}
                  <div>
                    <ButtonLink
                      to={`/admin/users/new?employee=${empId}`}
                      tone="secondary" size="sm"
                    >
                      Create a login for this employee
                    </ButtonLink>
                  </div>
                </div>
              )}
            </Section>
          </Card>
        )}

        <div style={{ display: "flex", gap: "0.6rem" }}>
          <Button type="submit" busy={busy} disabled={busy}>
            {busy ? "Saving…" : (isEdit ? "Save Changes" : "Create Employee")}
          </Button>
          <Button
            type="button" tone="secondary"
            onClick={() => guard.confirmLeave(() => navigate("/employees"))}
            disabled={busy}
          >
            Cancel
          </Button>
        </div>
      </form>

      <ConfirmDialog {...guard.dialogProps} />
      <ConfirmDialog
        open={confirmUnlink}
        title="Unlink login"
        message="Detach this login from the employee? The account itself stays active — deactivate it from the login form if they should lose access."
        confirmLabel="Unlink"
        confirmTone="danger"
        busy={busy}
        onConfirm={() => { void onUnlink(); }}
        onCancel={() => setConfirmUnlink(false)}
      />
    </PageShell>
  );
}
