import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  createBatch,
  updateBatch,
  useBatch,
  type BatchWriteBody,
} from "../api/batches";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Button, ButtonLink, Card, Field, FormActions, Input, Loading,
  MoneyInput, PageHeader, PageShell, Select, Textarea,
} from "../components/ui";
import styles from "./BatchForm.module.css";

// Combined New/Edit form for ACH batches at /app/batches/new
// and /app/batches/:id/edit. Mirrors the legacy batch_form.html
// Jinja form. Server handles unique-ref check + cross-tenant
// 404 + admin-role gate.

const COMPANIES = [
  "Intermex", "Maxi", "Barri", "Sigue", "Vigo", "Western Union",
  "MoneyGram", "Cibao", "RIA", "Other",
];
const STATUSES = ["Pending", "Cleared", "Returned", "Held"];

function todayIso() {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function BatchForm() {
  const { id } = useParams<{ id?: string }>();
  const isEdit = id !== undefined;
  const batchId = isEdit ? Number(id) : NaN;
  const navigate = useNavigate();
  const identity = getCurrentIdentity();

  const detail = useBatch(isEdit ? batchId : undefined);

  const [form, setForm] = useState<BatchWriteBody>({
    ach_date:       todayIso(),
    company:        COMPANIES[0],
    batch_ref:      "",
    ach_amount:     0,
    transfer_dates: "",
    status:         "Pending",
    reconciled:     false,
    notes:          "",
  });
  const [busy,  setBusy]  = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [field, setField] = useState<string | null>(null);

  // Hydrate form from existing batch on edit.
  useEffect(() => {
    if (!isEdit || !detail.data) return;
    const b = detail.data.batch;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable form from server-fetched batch on edit
    setForm({
      ach_date:       b.ach_date,
      company:        b.company,
      batch_ref:      b.batch_ref,
      ach_amount:     b.ach_amount,
      transfer_dates: b.transfer_dates,
      status:         b.status,
      reconciled:     b.reconciled,
      notes:          b.notes,
    });
  }, [isEdit, detail.data]);

  function set<K extends keyof BatchWriteBody>(
    key: K, value: BatchWriteBody[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null); setField(null);
    setBusy(true);
    try {
      const body: BatchWriteBody = {
        ...form,
        ach_amount: Number(form.ach_amount) || 0,
      };
      const result = isEdit
        ? await updateBatch(batchId, body)
        : await createBatch(body);
      navigate(`/batches`, { replace: true });
      void result;
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        if (err.body && typeof err.body === "object" && "detail" in err.body) {
          const detail = (err.body as Record<string, unknown>).detail;
          if (
            detail &&
            typeof detail === "object" &&
            "field" in (detail as Record<string, unknown>)
          ) {
            setField(String((detail as Record<string, unknown>).field));
          }
        }
      } else {
        setError("Could not save batch.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="62rem">
        <PageHeader title={isEdit ? "Edit batch" : "New ACH batch"} />
        <p>Sign in as a store admin to manage ACH batches.</p>
      </PageShell>
    );
  }

  if (isEdit && (detail.isLoading || !detail.data)) {
    return <PageShell maxWidth="62rem"><Loading /></PageShell>;
  }

  return (
    <PageShell maxWidth="62rem">
      <PageHeader
        title={isEdit ? `Edit batch #${batchId}` : "New ACH batch"}
        subtitle="Track an ACH withdrawal from a money-transfer company."
      />

      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      >
        <Card>
          <div className={styles.fieldGrid}>
            <Field label="ACH date" highlight={field === "ach_date"}>
              <Input type="date" required
                value={form.ach_date}
                onChange={(e) => set("ach_date", e.target.value)} />
            </Field>
            <Field label="Company">
              <Select value={form.company}
                onChange={(e) => set("company", e.target.value)}>
                {COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </Field>
            <Field label="Batch ref" highlight={field === "batch_ref"}>
              <Input type="text" required
                value={form.batch_ref}
                onChange={(e) => set("batch_ref", e.target.value)}
                placeholder="From bank statement" />
            </Field>
            <MoneyInput
              label="ACH amount"
              value={form.ach_amount}
              onChange={(v) => set("ach_amount", v)}
            />
            <Field label="Status">
              <Select value={form.status}
                onChange={(e) => set("status", e.target.value)}>
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </Select>
            </Field>
            <Field label="Reconciled">
              <Select
                value={form.reconciled ? "yes" : "no"}
                onChange={(e) => set("reconciled", e.target.value === "yes")}
              >
                <option value="no">No</option>
                <option value="yes">Yes</option>
              </Select>
            </Field>
            <Field label="Transfer dates (optional)">
              <Input type="text"
                value={form.transfer_dates}
                onChange={(e) => set("transfer_dates", e.target.value)}
                placeholder="e.g. 2026-03-10..14" />
            </Field>
          </div>
          <Field label="Notes (optional)">
            <Textarea
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              rows={3}
            />
          </Field>
        </Card>

        {error && <Alert tone="error">{error}</Alert>}

        <FormActions>
          <ButtonLink href="/batches" tone="secondary">Cancel</ButtonLink>
          <Button
            type="submit" busy={busy}
            disabled={busy || !form.batch_ref || !form.ach_date}
          >
            {busy ? "Saving…" : isEdit ? "Save changes" : "Create batch"}
          </Button>
        </FormActions>
      </form>
    </PageShell>
  );
}
