import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  createReturnCheck,
  createReturnCheckPayment,
  deleteReturnCheckPayment,
  markFraud,
  markLoss,
  reopenReturnCheck,
  updateReturnCheck,
  useReturnCheck,
  useReturnCheckPayments,
  type ReturnCheckPaymentRow,
  type ReturnCheckWriteBody,
} from "../api/returnChecks";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Button, ButtonLink, Card, EmptyState, Field, FormActions, Input,
  Loading, PageHeader, PageShell, SectionTitle, Select, space, Table, Textarea,
  tdStyle, thStyle,
} from "../components/ui";
import styles from "./ReturnCheckForm.module.css";

const PAYMENT_METHODS: Array<{ value: string; label: string }> = [
  { value: "cash",        label: "Cash"        },
  { value: "check",       label: "Check"       },
  { value: "zelle",       label: "Zelle"       },
  { value: "wire",        label: "Wire"        },
  { value: "money_order", label: "Money order" },
  { value: "other",       label: "Other"       },
];

// Combined New/Edit form for return checks at /app/return-checks/new
// and /app/return-checks/:id/edit. Edit variant also surfaces
// status-transition buttons (Mark loss / Mark fraud / Reopen) and
// an existing-payments table.
//
// Per-payment write endpoints (record / delete) ship in a follow-
// up PR — here we only show what's already on file.

function todayIso() {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function ReturnCheckForm() {
  const { id } = useParams<{ id?: string }>();
  const isEdit = id !== undefined;
  const rcId = isEdit ? Number(id) : NaN;
  const navigate = useNavigate();
  const identity = getCurrentIdentity();

  const detail = useReturnCheck(isEdit ? rcId : undefined);
  const payments = useReturnCheckPayments(isEdit ? rcId : undefined);

  const [form, setForm] = useState<ReturnCheckWriteBody>({
    bounced_on:    todayIso(),
    customer_name: "",
    check_number:  "",
    payer_bank:    "",
    amount:        0,
    notes:         "",
  });
  const [busy,  setBusy]  = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [field, setField] = useState<string | null>(null);

  useEffect(() => {
    if (!isEdit || !detail.data) return;
    const r = detail.data.return_check;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable form from server-fetched return-check on edit
    setForm({
      bounced_on:    r.bounced_on,
      customer_name: r.customer_name,
      check_number:  r.check_number,
      payer_bank:    r.payer_bank,
      amount:        r.amount,
      notes:         r.notes,
    });
  }, [isEdit, detail.data]);

  function set<K extends keyof ReturnCheckWriteBody>(
    key: K, value: ReturnCheckWriteBody[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null); setField(null);
    setBusy(true);
    try {
      const body: ReturnCheckWriteBody = {
        ...form,
        amount: Number(form.amount) || 0,
      };
      if (isEdit) await updateReturnCheck(rcId, body);
      else        await createReturnCheck(body);
      navigate("/return-checks", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        if (err.body && typeof err.body === "object" && "detail" in err.body) {
          const d = (err.body as Record<string, unknown>).detail;
          if (
            d && typeof d === "object" && "field" in (d as Record<string, unknown>)
          ) {
            setField(String((d as Record<string, unknown>).field));
          }
        }
      } else {
        setError("Could not save return check.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function transition(fn: (id: number) => Promise<unknown>, label: string) {
    if (!isEdit) return;
    if (!confirm(`${label} this return check?`)) return;
    setError(null); setBusy(true);
    try {
      await fn(rcId);
      await detail.refetch();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : `Could not ${label.toLowerCase()}.`,
      );
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="62rem">
        <PageHeader title={isEdit ? "Edit return check" : "New return check"} />
        <p>Sign in as a store admin to manage return checks.</p>
      </PageShell>
    );
  }

  if (isEdit && (detail.isLoading || !detail.data)) {
    return <PageShell maxWidth="62rem"><Loading /></PageShell>;
  }

  const status = isEdit ? detail.data?.return_check.status ?? "pending" : "pending";
  const recovered = isEdit ? detail.data?.return_check.recovered_total ?? 0 : 0;

  return (
    <PageShell maxWidth="62rem">
      <PageHeader
        title={isEdit ? `Return check #${rcId}` : "New return check"}
        subtitle="Track a bounced check from a customer and any partial recovery."
      />

      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      >
        <Card>
          <div className={styles.fieldGrid}>
            <Field label="Bounced on" highlight={field === "bounced_on"}>
              <Input type="date" required
                value={form.bounced_on}
                onChange={(e) => set("bounced_on", e.target.value)} />
            </Field>
            <Field label="Customer name" highlight={field === "customer_name"}>
              <Input type="text" required
                value={form.customer_name}
                onChange={(e) => set("customer_name", e.target.value)} />
            </Field>
            <Field label="Check number">
              <Input type="text"
                value={form.check_number ?? ""}
                onChange={(e) => set("check_number", e.target.value)} />
            </Field>
            <Field label="Payer bank">
              <Input type="text"
                value={form.payer_bank ?? ""}
                onChange={(e) => set("payer_bank", e.target.value)} />
            </Field>
            <Field label="Amount (USD)" highlight={field === "amount"}>
              <Input type="number" step="0.01" min="0.01" required
                value={form.amount}
                onChange={(e) => set("amount", Number(e.target.value))} />
            </Field>
          </div>
          <Field label="Notes (optional)">
            <Textarea
              value={form.notes ?? ""}
              onChange={(e) => set("notes", e.target.value)}
              rows={3}
            />
          </Field>
        </Card>

        {error && <Alert tone="error">{error}</Alert>}

        <FormActions>
          <ButtonLink href="/return-checks" tone="secondary">Cancel</ButtonLink>
          <Button
            type="submit" busy={busy}
            disabled={busy || !form.customer_name || !form.bounced_on}
          >
            {busy ? "Saving…" : isEdit ? "Save changes" : "Create return check"}
          </Button>
        </FormActions>
      </form>

      {isEdit && (
        <Card style={{ marginTop: space.lg }}>
          <SectionTitle>Status</SectionTitle>
          <p className={styles.statusLine}>
            Current: <strong className={styles.statusName}>{status}</strong>
            {" · "}Recovered <span className={styles.mono}>${recovered.toFixed(2)}</span>
            {" of "}<span className={styles.mono}>${form.amount.toFixed(2)}</span>
          </p>
          <div className={styles.transitionRow}>
            {status === "pending" && (
              <>
                <Button
                  tone="danger"
                  onClick={() => transition(markLoss, "Mark loss")}
                  disabled={busy}
                >
                  Mark loss
                </Button>
                <Button
                  tone="danger"
                  onClick={() => transition(markFraud, "Mark fraud")}
                  disabled={busy}
                >
                  Mark fraud
                </Button>
              </>
            )}
            {status !== "pending" && (
              <Button
                tone="secondary"
                onClick={() => transition(reopenReturnCheck, "Reopen")}
                disabled={busy}
              >
                Reopen
              </Button>
            )}
          </div>
        </Card>
      )}

      {isEdit && (
        <Card style={{ marginTop: space.lg }}>
          <SectionTitle>Recovery payments</SectionTitle>
          {status === "pending" && (
            <RecordPaymentForm
              rcId={rcId}
              remaining={Math.max(0, form.amount - recovered)}
              disabled={busy}
            />
          )}
          {(status === "loss" || status === "fraud") && (
            <p className={styles.statusLine}>
              This check is closed as <strong>{status}</strong>.
              Reopen above to record additional payments.
            </p>
          )}
          {payments.isLoading && <Loading />}
          {payments.data && payments.data.payments.length === 0 && (
            <EmptyState title="No recovery payments recorded." />
          )}
          {payments.data && payments.data.payments.length > 0 && (
            <PaymentsTable
              rows={payments.data.payments}
              rcId={rcId}
              canDelete={status !== "loss" && status !== "fraud"}
            />
          )}
        </Card>
      )}
    </PageShell>
  );
}


function RecordPaymentForm({
  rcId, remaining, disabled,
}: {
  rcId: number;
  remaining: number;
  disabled: boolean;
}) {
  const qc = useQueryClient();
  const identity = getCurrentIdentity();
  const [paidOn,  setPaidOn]  = useState(() => todayIso());
  const [amount,  setAmount]  = useState("");
  const [method,  setMethod]  = useState<string>(PAYMENT_METHODS[0].value);
  const [note,    setNote]    = useState("");
  const [busy,    setBusy]    = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  // The remaining cap is enforced server-side too, but render the
  // limit hint so a cashier doesn't tab over to a calculator.
  const cap = remaining;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const amt = Number(amount);
    if (!Number.isFinite(amt) || amt <= 0) {
      setError("Amount must be greater than zero.");
      return;
    }
    if (cap <= 0) {
      setError("Return check is already fully recovered.");
      return;
    }
    setBusy(true);
    try {
      await createReturnCheckPayment(rcId, {
        paid_on: paidOn,
        amount: amt,
        method,
        note,
      });
      // Refetch parent + payments so the totals strip + table flip.
      qc.invalidateQueries({
        queryKey: ["return-checks", "detail", identity?.store_id, rcId],
      });
      qc.invalidateQueries({
        queryKey: ["return-checks", "payments", identity?.store_id, rcId],
      });
      setAmount(""); setNote("");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not record payment.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className={styles.paymentForm}>
      <div className={styles.paymentFormGrid}>
        <Field label="Date">
          <Input
            type="date" required
            value={paidOn}
            onChange={(e) => setPaidOn(e.target.value)}
            disabled={busy || disabled}
          />
        </Field>
        <Field
          label="Amount (USD)"
          hint={cap > 0 ? `Up to $${cap.toFixed(2)} remaining.` : undefined}
        >
          <Input
            type="number" step="0.01" min="0.01" max={cap || undefined}
            required
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            disabled={busy || disabled || cap <= 0}
          />
        </Field>
        <Field label="Method">
          <Select
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            disabled={busy || disabled}
          >
            {PAYMENT_METHODS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </Select>
        </Field>
        <Field label="Note (optional)">
          <Input
            type="text" maxLength={200}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={busy || disabled}
            placeholder="e.g. paid in cash at counter"
          />
        </Field>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <div className={styles.paymentFormActions}>
        <Button
          type="submit" busy={busy}
          disabled={busy || disabled || cap <= 0 || !amount}
        >
          {busy ? "Recording…" : "Record payment"}
        </Button>
      </div>
    </form>
  );
}


function PaymentsTable({
  rows, rcId, canDelete,
}: {
  rows: ReturnCheckPaymentRow[];
  rcId: number;
  canDelete: boolean;
}) {
  const qc = useQueryClient();
  const identity = getCurrentIdentity();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onDelete(p: ReturnCheckPaymentRow) {
    if (!confirm(`Remove the $${p.amount.toFixed(2)} payment from ${p.paid_on}?`)) {
      return;
    }
    setError(null);
    setBusyId(p.id);
    try {
      await deleteReturnCheckPayment(rcId, p.id);
      qc.invalidateQueries({
        queryKey: ["return-checks", "detail", identity?.store_id, rcId],
      });
      qc.invalidateQueries({
        queryKey: ["return-checks", "payments", identity?.store_id, rcId],
      });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not remove payment.",
      );
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      {error && <Alert tone="error">{error}</Alert>}
      <Table>
        <thead>
          <tr>
            <th style={thStyle}>Paid on</th>
            <th style={{ ...thStyle, textAlign: "right" }}>Amount</th>
            <th style={thStyle}>Method</th>
            <th style={thStyle}>Notes</th>
            {canDelete && <th style={thStyle} aria-label="actions" />}
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td style={tdStyle}>
                <span className={styles.monoMuted}>{p.paid_on}</span>
              </td>
              <td style={{ ...tdStyle, textAlign: "right" }}>
                <span className={styles.mono}>${p.amount.toFixed(2)}</span>
              </td>
              <td style={tdStyle}>{p.method || "—"}</td>
              <td style={tdStyle}>{p.notes || "—"}</td>
              {canDelete && (
                <td style={{ ...tdStyle, textAlign: "right" }}>
                  <Button
                    tone="danger" size="sm"
                    busy={busyId === p.id}
                    disabled={busyId !== null}
                    onClick={() => onDelete(p)}
                  >
                    {busyId === p.id ? "Removing…" : "Remove"}
                  </Button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </Table>
    </>
  );
}


