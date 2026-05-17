import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import SenderAutocomplete from "../components/SenderAutocomplete";
import RecipientSuggestions from "../components/RecipientSuggestions";
import {
  Alert, Button, Card, ErrorState, Field, FormActions, Input,
  Loading, PageHeader, PageShell, Select,
} from "../components/ui";
import {
  previewFederalTax,
  updateTransfer,
  useEmployees,
  useTransfer,
  type CreateTransferBody,
} from "../api/transfers";
import { useStoreInfo } from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./EditTransfer.module.css";

// Edit-transfer page at /app/transfers/:id/edit. Loads the
// existing transfer via the read-side hook, lets the user mutate
// any field, posts the full body to PUT /api/v2/transfers/{id}.
//
// Server-side recomputes federal_tax from
// (send_amount, service_type, country, store) — same invariant
// as create.

const COMPANIES = [
  "Intermex", "Maxi", "Barri", "Sigue", "Vigo", "Western Union",
  "MoneyGram", "Cibao", "RIA", "Other",
];
const SERVICES = [
  "Money Transfer", "Bill Payment", "Top Up", "Recharge",
];
const COUNTRIES = [
  "United States", "Mexico", "Guatemala", "El Salvador", "Honduras",
  "Dominican Republic", "Colombia", "Ecuador", "Peru", "Other",
];
const STATUSES = ["Sent", "Pending", "Cancelled", "Returned"];

export default function EditTransfer() {
  const { id } = useParams<{ id: string }>();
  const transferId = id ? Number(id) : NaN;
  const navigate = useNavigate();
  const identity = getCurrentIdentity();
  const detail = useTransfer(Number.isFinite(transferId) ? transferId : undefined);
  const roster = useEmployees();
  const storeInfo = useStoreInfo();

  const [form, setForm] = useState<CreateTransferBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hydrate the form once the existing transfer arrives. Edits
  // happen on the form copy — only a successful PUT writes back.
  useEffect(() => {
    if (!detail.data) return;
    const t = detail.data.transfer;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable form from server-fetched transfer on edit
    setForm({
      send_date: t.send_date,
      company: t.company || COMPANIES[0],
      service_type: t.service_type || "Money Transfer",
      sender_name: "",
      sender_phone: "",
      sender_phone_country: "+1",
      sender_address: "",
      send_amount: t.send_amount,
      fee: t.fee,
      country: t.country || "Mexico",
      recipient_name: t.recipient_name || "",
      recipient_phone: "",
      confirm_number: t.confirm_number || "",
      status: t.status || "Sent",
      employee_id: null,  // user re-confirms on save
      batch_id: t.batch_id || "",
    });
  }, [detail.data]);

  function set<K extends keyof CreateTransferBody>(
    key: K,
    value: CreateTransferBody[K],
  ) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form || !Number.isFinite(transferId)) return;
    setError(null);
    setBusy(true);
    try {
      const result = await updateTransfer(transferId, {
        ...form,
        send_amount: Number(form.send_amount) || 0,
        fee: Number(form.fee) || 0,
      });
      navigate(`/transfers/${result.transfer.id}`, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not save the changes. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="62rem">
        <PageHeader title="Edit transfer" />
        <p>Sign in as a store admin to edit transfers.</p>
      </PageShell>
    );
  }

  if (!Number.isFinite(transferId)) {
    return (
      <PageShell maxWidth="62rem">
        <p>Invalid transfer ID.</p>
      </PageShell>
    );
  }

  if (detail.isLoading || form == null) {
    return (
      <PageShell maxWidth="62rem">
        <Loading />
      </PageShell>
    );
  }

  if (detail.isError) {
    return (
      <PageShell maxWidth="62rem">
        <ErrorState
          message={
            detail.error instanceof Error
              ? detail.error.message
              : "Could not load this transfer."
          }
          onRetry={() => { void detail.refetch(); }}
        />
      </PageShell>
    );
  }

  // Print-receipt action is intentionally hidden — see App.tsx
  // comment near the (now-disabled) receipt route. The
  // ButtonLink + ``/app/transfers/{id}/receipt`` href can come back
  // by reverting this commit if we ever decide a customer-facing
  // receipt belongs in a ledger product.
  return (
    <PageShell maxWidth="62rem">
      <PageHeader
        title={`Edit transfer #${transferId}`}
        subtitle="Federal tax is recomputed server-side on save."
      />

      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      >
        <Card>
          <h2 className={styles.sectionTitle}>When + how</h2>
          <div className={styles.grid}>
            <Field label="Date">
              <Input type="date" value={form.send_date}
                onChange={(e) => set("send_date", e.target.value)} required />
            </Field>
            <Field label="Company">
              <Select value={form.company}
                onChange={(e) => set("company", e.target.value)}>
                {COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </Field>
            <Field label="Service">
              <Select value={form.service_type}
                onChange={(e) => set("service_type", e.target.value)}>
                {SERVICES.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </Field>
            <Field label="Status">
              <Select value={form.status}
                onChange={(e) => set("status", e.target.value)}>
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </Select>
            </Field>
          </div>
        </Card>

        <Card>
          <h2 className={styles.sectionTitle}>Sender</h2>
          <div className={styles.grid}>
            <Field label="Full name">
              <SenderAutocomplete
                value={form.sender_name}
                onChange={(v) => set("sender_name", v)}
                onPick={(row) => {
                  setForm((f) =>
                    f
                      ? {
                          ...f,
                          sender_name: row.full_name,
                          sender_phone_country: row.phone_country || "+1",
                          sender_phone: row.phone_number,
                          sender_address: row.address,
                          sender_dob: row.dob || "",
                          customer_id: row.id,
                        }
                      : f,
                  );
                }}
                onClearPickedId={() => set("customer_id", null)}
                required
              />
            </Field>
            <Field label="Phone country">
              <Input type="text" value={form.sender_phone_country}
                onChange={(e) => set("sender_phone_country", e.target.value)}
                placeholder="+1" />
            </Field>
            <Field label="Phone">
              <Input type="tel" value={form.sender_phone}
                onChange={(e) => set("sender_phone", e.target.value)} />
            </Field>
            <Field label="Address">
              <Input type="text" value={form.sender_address}
                onChange={(e) => set("sender_address", e.target.value)} />
            </Field>
          </div>
          {form.customer_id && (
            <p className={styles.note}>
              Linked to customer #{form.customer_id} — edits sync
              back to the customer directory.
            </p>
          )}
        </Card>

        <Card>
          <h2 className={styles.sectionTitle}>Recipient</h2>
          <RecipientSuggestions
            customerId={form.customer_id ?? null}
            storeId={identity.store_id}
            onPick={(row) => {
              set("recipient_name", row.name);
              if (row.country && (COUNTRIES as readonly string[]).includes(row.country)) {
                set("country", row.country);
              }
              set("recipient_phone", row.phone);
            }}
          />
          <div className={styles.grid}>
            <Field label="Country">
              <Select value={form.country}
                onChange={(e) => set("country", e.target.value)}>
                {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </Field>
            <Field label="Recipient name">
              <Input type="text" value={form.recipient_name}
                onChange={(e) => set("recipient_name", e.target.value)} />
            </Field>
            <Field label="Recipient phone">
              <Input type="tel" value={form.recipient_phone}
                onChange={(e) => set("recipient_phone", e.target.value)} />
            </Field>
          </div>
        </Card>

        <Card>
          <h2 className={styles.sectionTitle}>Amounts</h2>
          <div className={styles.grid}>
            <Field label="Send amount (USD)">
              <Input type="number" step="0.01" min="0"
                value={form.send_amount}
                onChange={(e) => set("send_amount", Number(e.target.value))}
                required />
            </Field>
            <Field label="Fee (USD)">
              <Input type="number" step="0.01" min="0"
                value={form.fee}
                onChange={(e) => set("fee", Number(e.target.value))} />
            </Field>
            <Field
              label={
                (storeInfo.data?.store.federal_tax_rate ?? 0) > 0
                  ? `Federal tax preview (${((storeInfo.data!.store.federal_tax_rate) * 100).toFixed(0)}%, server recomputes)`
                  : "Federal tax preview"
              }
            >
              <Input
                type="text"
                readOnly
                tabIndex={-1}
                value={`$${previewFederalTax({
                  sendAmount: form.send_amount,
                  serviceType: form.service_type,
                  country: form.country,
                  rate: storeInfo.data?.store.federal_tax_rate ?? 0,
                }).toFixed(2)}`}
                className={styles.taxPreview}
              />
            </Field>
            <Field label="Confirm #">
              <Input type="text" value={form.confirm_number}
                onChange={(e) => set("confirm_number", e.target.value)} />
            </Field>
          </div>
        </Card>

        <Card>
          <h2 className={styles.sectionTitle}>Processed by</h2>
          <div className={styles.grid}>
            <Field label="Employee">
              <Select
                value={form.employee_id ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  set("employee_id", v ? Number(v) : null);
                }}
                required
                disabled={roster.isLoading}
              >
                <option value="">— Select —</option>
                {roster.data?.employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>{emp.name}</option>
                ))}
              </Select>
            </Field>
          </div>
          <p className={styles.note}>
            Required: who made this edit.
          </p>
        </Card>

        {error && <Alert tone="error">{error}</Alert>}

        <FormActions>
          <Button
            tone="secondary"
            onClick={() => navigate(`/transfers/${transferId}`)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            busy={busy}
            disabled={busy || !form.sender_name || !form.send_amount || !form.employee_id}
          >
            {busy ? "Saving…" : "Save changes"}
          </Button>
        </FormActions>
      </form>
    </PageShell>
  );
}
