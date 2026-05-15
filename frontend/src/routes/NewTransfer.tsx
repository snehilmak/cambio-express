import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import SenderAutocomplete from "../components/SenderAutocomplete";
import {
  Button,
  Card,
  Field,
  FormActions,
  Input,
  PageHeader,
  PageShell,
  Section,
  Select,
  tokens,
} from "../components/ui";
import {
  createTransfer,
  previewFederalTax,
  useEmployees,
  type CreateTransferBody,
} from "../api/transfers";
import { useStoreInfo } from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

// New transfer form at /app/transfers/new.
//
// **Canonical example** for the SPA component-library migration
// (P2 #9). This file demonstrates how a route migrates from inline
// style constants to the kit primitives in
// ``frontend/src/components/ui``: ``PageShell``, ``PageHeader``,
// ``Section``, ``Card``, ``Field``, ``Input``, ``Select``, ``Button``,
// ``FormActions``. Other heavily-inlined routes (BatchForm,
// EditTransfer, EditMonthly, Settings, AdminSubscription, …)
// migrate on-touch following this pattern.

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

function todayIso() {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function NewTransfer() {
  const navigate = useNavigate();
  const identity = getCurrentIdentity();
  const roster = useEmployees();
  const storeInfo = useStoreInfo();

  const [form, setForm] = useState<CreateTransferBody>({
    send_date: todayIso(),
    company: COMPANIES[0],
    service_type: "Money Transfer",
    sender_name: "",
    sender_phone_country: "+1",
    sender_phone: "",
    send_amount: 0,
    fee: 0,
    country: "Mexico",
    recipient_name: "",
    recipient_phone: "",
    confirm_number: "",
    status: "Sent",
    employee_id: null,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof CreateTransferBody>(
    key: K,
    value: CreateTransferBody[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await createTransfer({
        ...form,
        // Coerce numeric fields — <input type="number"> gives
        // strings on some browsers.
        send_amount: Number(form.send_amount) || 0,
        fee: Number(form.fee) || 0,
      });
      navigate(`/transfers/${result.transfer.id}`, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not save the transfer. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell>
        <PageHeader title="New transfer" />
        <p style={{ color: tokens.textMuted, textAlign: "center", padding: "1.5rem 0" }}>
          Sign in as a store admin to create transfers. Owners + the
          store-picker land in a follow-up PR.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="New transfer"
        subtitle={
          "Federal tax preview updates as you type; the server "
          + "recomputes the final value on save."
        }
      />

      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      >
        <Card>
          <Section title="When + how">
            <Grid>
              <Field label="Date">
                <Input
                  type="date"
                  value={form.send_date}
                  onChange={(e) => set("send_date", e.target.value)}
                  required
                />
              </Field>
              <Field label="Company">
                <Select
                  value={form.company}
                  onChange={(e) => set("company", e.target.value)}
                >
                  {COMPANIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Service">
                <Select
                  value={form.service_type}
                  onChange={(e) => set("service_type", e.target.value)}
                >
                  {SERVICES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Status">
                <Select
                  value={form.status}
                  onChange={(e) => set("status", e.target.value)}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </Select>
              </Field>
            </Grid>
          </Section>
        </Card>

        <Card>
          <Section title="Sender">
            <Grid>
              <Field label="Full name">
                <SenderAutocomplete
                  value={form.sender_name}
                  onChange={(v) => set("sender_name", v)}
                  onPick={(row) => {
                    // Autofill the rest of the sender block from the
                    // picked customer row + remember the customer_id
                    // so the upsert reuses the same record.
                    setForm((f) => ({
                      ...f,
                      sender_name: row.full_name,
                      sender_phone_country: row.phone_country || "+1",
                      sender_phone: row.phone_number,
                      sender_address: row.address,
                      sender_dob: row.dob || "",
                      customer_id: row.id,
                    }));
                  }}
                  onClearPickedId={() => set("customer_id", null)}
                  required
                />
              </Field>
              <Field label="Phone country">
                <Input
                  type="text"
                  value={form.sender_phone_country}
                  onChange={(e) => set("sender_phone_country", e.target.value)}
                  placeholder="+1"
                />
              </Field>
              <Field label="Phone">
                <Input
                  type="tel"
                  value={form.sender_phone}
                  onChange={(e) => set("sender_phone", e.target.value)}
                />
              </Field>
              <Field label="Address">
                <Input
                  type="text"
                  value={form.sender_address}
                  onChange={(e) => set("sender_address", e.target.value)}
                />
              </Field>
            </Grid>
            {form.customer_id && (
              <p
                style={{
                  margin: "0.5rem 0 0",
                  fontSize: "0.85rem",
                  color: tokens.textMuted,
                }}
              >
                Linked to customer #{form.customer_id} — edits sync
                back to the customer directory.
              </p>
            )}
          </Section>
        </Card>

        <Card>
          <Section title="Recipient">
            <Grid>
              <Field label="Country">
                <Select
                  value={form.country}
                  onChange={(e) => set("country", e.target.value)}
                >
                  {COUNTRIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Recipient name">
                <Input
                  type="text"
                  value={form.recipient_name}
                  onChange={(e) => set("recipient_name", e.target.value)}
                />
              </Field>
              <Field label="Recipient phone">
                <Input
                  type="tel"
                  value={form.recipient_phone}
                  onChange={(e) => set("recipient_phone", e.target.value)}
                />
              </Field>
            </Grid>
          </Section>
        </Card>

        <Card>
          <Section title="Amounts">
            <Grid>
              <Field label="Send amount (USD)">
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.send_amount}
                  onChange={(e) =>
                    set("send_amount", Number(e.target.value))
                  }
                  required
                />
              </Field>
              <Field label="Fee (USD)">
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.fee}
                  onChange={(e) => set("fee", Number(e.target.value))}
                />
              </Field>
              <FederalTaxPreview
                sendAmount={form.send_amount}
                serviceType={form.service_type}
                country={form.country ?? ""}
                rate={storeInfo.data?.store.federal_tax_rate ?? 0}
              />
              <Field label="Confirm #">
                <Input
                  type="text"
                  value={form.confirm_number}
                  onChange={(e) => set("confirm_number", e.target.value)}
                />
              </Field>
            </Grid>
          </Section>
        </Card>

        <Card>
          <Section title="Processed by">
            <Grid>
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
                    <option key={emp.id} value={emp.id}>
                      {emp.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </Grid>
            {roster.isError && (
              <p
                style={{
                  margin: "0.5rem 0 0",
                  fontSize: "0.85rem",
                  color: tokens.negative,
                }}
              >
                Couldn't load roster. Add cashiers via Settings → Team
                on the legacy admin page.
              </p>
            )}
            {!roster.isLoading &&
              !roster.isError &&
              roster.data &&
              roster.data.employees.length === 0 && (
                <p
                  style={{
                    margin: "0.5rem 0 0",
                    fontSize: "0.85rem",
                    color: tokens.textMuted,
                  }}
                >
                  No active employees on this store's roster yet. Add
                  them via Settings → Team on the legacy admin page.
                </p>
              )}
          </Section>
        </Card>

        {error && (
          <p role="alert" style={{ color: tokens.negative, textAlign: "center", padding: "0.5rem 0" }}>
            {error}
          </p>
        )}

        <FormActions>
          <Button
            tone="secondary"
            onClick={() => navigate("/transfers")}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            busy={busy}
            disabled={busy || !form.sender_name || !form.send_amount}
          >
            {busy ? "Saving…" : "Save transfer"}
          </Button>
        </FormActions>
      </form>
    </PageShell>
  );
}


// Auto-fit grid for the form rows — repeated four times above so it
// pays its keep as a local helper, not yet generic enough for the
// kit.
function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))",
        gap: "0.75rem",
      }}
    >
      {children}
    </div>
  );
}

// Read-only client-side preview of the federal tax the server is
// about to compute. Mirrors the rule in
// `api/Modules/Transfers/Services/tax.py` so the cashier can
// sanity-check the number before submit; the actual value still
// comes from the server (CLAUDE.md invariant #9).
function FederalTaxPreview({
  sendAmount, serviceType, country, rate,
}: {
  sendAmount: number | string;
  serviceType: string;
  country: string;
  rate: number;
}) {
  const tax = previewFederalTax({
    sendAmount, serviceType, country, rate,
  });
  const exempt = tax === 0 && (Number(sendAmount) || 0) > 0;
  const pct = (rate * 100).toFixed(rate < 0.01 ? 2 : 0);
  return (
    <Field
      label={
        rate > 0
          ? `Federal tax preview (${pct}%, server recomputes)`
          : "Federal tax preview"
      }
    >
      <Input
        type="text"
        readOnly
        tabIndex={-1}
        value={`$${tax.toFixed(2)}`}
        style={{
          background: tokens.surface2,
          color: tokens.textMuted,
          cursor: "default",
          fontFamily: tokens.fontMono,
        }}
      />
      {exempt && (
        <span
          style={{
            display: "block",
            marginTop: "0.25rem",
            fontSize: "0.75rem",
            color: tokens.textMuted,
          }}
        >
          Exempt — {country === "United States"
            ? "domestic recipient"
            : `${serviceType} service`}
        </span>
      )}
    </Field>
  );
}
