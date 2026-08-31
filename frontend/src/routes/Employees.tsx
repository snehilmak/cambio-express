import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  createEmployee, updateEmployee, useEmployees,
  type EmployeeRow, type LoginOnlyRow,
} from "../api/employees";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { formatDate } from "../lib/datetime";
import { fmtMoney2 } from "../lib/formatters";
import {
  Breadcrumbs, ButtonLink, Card, ConfirmDialog, Empty, PageHeader,
  PageShell, Pill, RowActions, Section, Table, TableStates, tdStyle,
  thStyle, useToast,
} from "../components/ui";

// /app/employees — the unified Employees hub (E-2). ONE place
// manages the person: HR record (payroll basics, personal
// details) + their optional login. Replaces the old Cashiers
// roster page and the Team Users page; /admin/users/* survives
// only as the login-credentials form the Login section links to.

export default function Employees() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useEmployees();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [confirmRow, setConfirmRow] = useState<EmployeeRow | null>(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["employees"] });
  }

  async function toggleActive(row: EmployeeRow) {
    setBusy(true);
    try {
      await updateEmployee(row.id, { is_active: !row.is_active });
      toast({
        message: row.is_active
          ? `${row.name} deactivated.`
          : `${row.name} reactivated.`,
        tone: "success",
      });
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not update the employee.",
        tone: "error",
      });
    } finally {
      setBusy(false);
      setConfirmRow(null);
    }
  }

  async function adoptLogin(row: LoginOnlyRow) {
    // "Create HR record" for a login-only account: mint the
    // employee row and link in one call.
    setBusy(true);
    try {
      const made = await createEmployee({
        name: row.full_name || row.username,
        user_id: row.user_id,
      });
      toast({ message: "Employee record created.", tone: "success" });
      refresh();
      navigate(`/employees/${made.id}/edit`);
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not create the employee record.",
        tone: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  if (
    !identity
    || (identity.role !== "admin" && identity.role !== "owner")
  ) {
    return (
      <PageShell>
        <PageHeader title="Employees" />
        <Empty>You need a store-admin sign-in to manage employees.</Empty>
      </PageShell>
    );
  }

  const rows = data?.rows ?? [];
  const loginOnly = data?.login_only ?? [];

  return (
    <PageShell>
      <Breadcrumbs crumbs={[{ label: "Employees" }]} />
      <PageHeader
        title="Employees"
        subtitle="Everyone who works here — profile, payroll, and login in one place."
        actions={(
          <ButtonLink href="/employees/new" tone="primary" size="sm">
            + Add Employee
          </ButtonLink>
        )}
      />

      <Card>
        <TableStates
          isLoading={isLoading} isError={isError} error={error}
          isEmpty={!!data && rows.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle="No employees yet"
          emptyBody='Click "+ Add Employee" to add your first person.'
          rows={4} cols={6}
        />
        {rows.length > 0 && (
          <Table>
            <thead>
              <tr>
                {["Name", "Login", "Rate", "Hired", "Status", ""].map((h) => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td style={tdStyle}><strong>{r.name}</strong></td>
                  <td style={tdStyle}>
                    {r.login ? (
                      <>
                        <Pill tone={r.login.role === "admin" ? "accent" : "neutral"}>
                          {r.login.role === "admin" ? "Super Admin" : "Employee"}
                        </Pill>{" "}
                        <span>{r.login.username}</span>
                        {r.login.has_custom_permissions && (
                          <>
                            {" "}
                            <Pill tone="neutral">Custom access</Pill>
                          </>
                        )}
                        {!r.login.is_active && (
                          <>
                            {" "}
                            <Pill tone="neutral">Login inactive</Pill>
                          </>
                        )}
                      </>
                    ) : (
                      <Pill tone="neutral">No login</Pill>
                    )}
                  </td>
                  <td style={tdStyle}>
                    {r.hourly_rate > 0 ? `${fmtMoney2(r.hourly_rate)}/hr` : "—"}
                  </td>
                  <td style={tdStyle}>
                    {r.hired_on ? formatDate(r.hired_on) : "—"}
                  </td>
                  <td style={tdStyle}>
                    <Pill tone={r.is_active ? "accent" : "neutral"}>
                      {r.is_active ? "Active" : "Inactive"}
                    </Pill>
                  </td>
                  <td style={{ ...tdStyle, textAlign: "right" }}>
                    <RowActions
                      title={r.name}
                      actions={[
                        {
                          label: "Edit",
                          onClick: () => navigate(`/employees/${r.id}/edit`),
                        },
                        r.is_active
                          ? {
                              label: "Deactivate", tone: "danger" as const,
                              onClick: () => setConfirmRow(r),
                              disabled: busy,
                            }
                          : {
                              label: "Reactivate",
                              onClick: () => { void toggleActive(r); },
                              disabled: busy,
                            },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {loginOnly.length > 0 && (
        <Section title="Logins without an employee record">
          <Card>
            <p style={{ marginTop: 0 }}>
              These accounts can sign in but have no HR record yet —
              create one so their payroll and personal details live
              here too.
            </p>
            <Table>
              <thead>
                <tr>
                  {["Login", "Name", "Role", ""].map((h) => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loginOnly.map((u) => (
                  <tr key={u.user_id}>
                    <td style={tdStyle}><strong>{u.username}</strong></td>
                    <td style={tdStyle}>{u.full_name || "—"}</td>
                    <td style={tdStyle}>
                      <Pill tone={u.role === "admin" ? "accent" : "neutral"}>
                        {u.role === "admin" ? "Super Admin" : "Employee"}
                      </Pill>
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right" }}>
                      <RowActions
                        title={u.username}
                        actions={[
                          {
                            label: "Create employee record",
                            onClick: () => { void adoptLogin(u); },
                            disabled: busy,
                          },
                        ]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </Section>
      )}

      <ConfirmDialog
        open={confirmRow != null}
        title="Deactivate employee"
        message={`Deactivate ${confirmRow?.name ?? "this employee"}? They disappear from attribution dropdowns and the time clock; history is kept. A linked login stays active — disable it from the Login section if they should also lose access.`}
        confirmLabel="Deactivate"
        confirmTone="danger"
        busy={busy}
        onConfirm={() => { if (confirmRow) void toggleActive(confirmRow); }}
        onCancel={() => setConfirmRow(null)}
      />
    </PageShell>
  );
}
