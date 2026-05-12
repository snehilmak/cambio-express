import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import SenderAutocomplete from "../components/SenderAutocomplete";
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
// Mirrors the legacy `transfer_form.html` Jinja form's required
// inputs. Server-side recomputes federal_tax — we don't expose it
// in the form. On success: redirect to /app/transfers/:new-id.
//
// First write-side screen on the SPA. Subsequent PRs add edit,
// daily book save, and the rest of the form-driven flows.

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>New transfer</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to create transfers. Owners + the
          store-picker land in a follow-up PR.
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>New transfer</h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
          }}
        >
          Federal tax preview updates as you type; the server
          recomputes the final value on save.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      >
        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>When + how</h2>
          <Grid>
            <Field label="Date">
              <input
                type="date"
                value={form.send_date}
                onChange={(e) => set("send_date", e.target.value)}
                style={inputStyle}
                required
              />
            </Field>
            <Field label="Company">
              <select
                value={form.company}
                onChange={(e) => set("company", e.target.value)}
                style={inputStyle}
              >
                {COMPANIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
            <Field label="Service">
              <select
                value={form.service_type}
                onChange={(e) => set("service_type", e.target.value)}
                style={inputStyle}
              >
                {SERVICES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
            <Field label="Status">
              <select
                value={form.status}
                onChange={(e) => set("status", e.target.value)}
                style={inputStyle}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </Field>
          </Grid>
        </section>

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Sender</h2>
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
              <input
                type="text"
                value={form.sender_phone_country}
                onChange={(e) => set("sender_phone_country", e.target.value)}
                placeholder="+1"
                style={inputStyle}
              />
            </Field>
            <Field label="Phone">
              <input
                type="tel"
                value={form.sender_phone}
                onChange={(e) => set("sender_phone", e.target.value)}
                style={inputStyle}
              />
            </Field>
            <Field label="Address">
              <input
                type="text"
                value={form.sender_address}
                onChange={(e) => set("sender_address", e.target.value)}
                style={inputStyle}
              />
            </Field>
          </Grid>
          {form.customer_id && (
            <p
              style={{
                margin: "0.5rem 0 0",
                fontSize: "0.85rem",
                color: "var(--db-text-muted, #a3a3a3)",
              }}
            >
              Linked to customer #{form.customer_id} — edits sync
              back to the customer directory.
            </p>
          )}
        </section>

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Recipient</h2>
          <Grid>
            <Field label="Country">
              <select
                value={form.country}
                onChange={(e) => set("country", e.target.value)}
                style={inputStyle}
              >
                {COUNTRIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
            <Field label="Recipient name">
              <input
                type="text"
                value={form.recipient_name}
                onChange={(e) => set("recipient_name", e.target.value)}
                style={inputStyle}
              />
            </Field>
            <Field label="Recipient phone">
              <input
                type="tel"
                value={form.recipient_phone}
                onChange={(e) => set("recipient_phone", e.target.value)}
                style={inputStyle}
              />
            </Field>
          </Grid>
        </section>

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Amounts</h2>
          <Grid>
            <Field label="Send amount (USD)">
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.send_amount}
                onChange={(e) =>
                  set("send_amount", Number(e.target.value))
                }
                style={inputStyle}
                required
              />
            </Field>
            <Field label="Fee (USD)">
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.fee}
                onChange={(e) => set("fee", Number(e.target.value))}
                style={inputStyle}
              />
            </Field>
            <FederalTaxPreview
              sendAmount={form.send_amount}
              serviceType={form.service_type}
              country={form.country ?? ""}
              rate={storeInfo.data?.store.federal_tax_rate ?? 0}
            />
            <Field label="Confirm #">
              <input
                type="text"
                value={form.confirm_number}
                onChange={(e) => set("confirm_number", e.target.value)}
                style={inputStyle}
              />
            </Field>
          </Grid>
        </section>

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Processed by</h2>
          <Grid>
            <Field label="Employee">
              <select
                value={form.employee_id ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  set("employee_id", v ? Number(v) : null);
                }}
                style={inputStyle}
                required
                disabled={roster.isLoading}
              >
                <option value="">— Select —</option>
                {roster.data?.employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.name}
                  </option>
                ))}
              </select>
            </Field>
          </Grid>
          {roster.isError && (
            <p
              style={{
                margin: "0.5rem 0 0",
                fontSize: "0.85rem",
                color: "var(--db-negative, #ff3b30)",
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
                  color: "var(--db-text-muted, #a3a3a3)",
                }}
              >
                No active employees on this store's roster yet. Add
                them via Settings → Team on the legacy admin page.
              </p>
            )}
        </section>

        {error && (
          <p
            role="alert"
            style={{ ...emptyStyle, color: "var(--db-negative, #ff3b30)" }}
          >
            {error}
          </p>
        )}

        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={() => navigate("/transfers")}
            style={cancelBtnStyle}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || !form.sender_name || !form.send_amount}
            style={{
              ...saveBtnStyle,
              opacity:
                busy || !form.sender_name || !form.send_amount ? 0.6 : 1,
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {busy ? "Saving…" : "Save transfer"}
          </button>
        </div>
      </form>
    </main>
  );
}

function Field({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <span
        style={{
          fontSize: "0.78rem",
          color: "var(--db-text-muted, #a3a3a3)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}

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
      <input
        type="text"
        readOnly
        tabIndex={-1}
        value={`$${tax.toFixed(2)}`}
        style={{
          ...inputStyle,
          background: "var(--db-surface-2, #141414)",
          color: "var(--db-text-muted, #a3a3a3)",
          cursor: "default",
          fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
        }}
      />
      {exempt && (
        <span
          style={{
            display: "block",
            marginTop: "0.25rem",
            fontSize: "0.75rem",
            color: "var(--db-text-muted, #a3a3a3)",
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

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2rem 1.5rem",
  maxWidth: "62rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.95rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--db-text-muted, #a3a3a3)",
  margin: "0 0 1rem",
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem 1.5rem",
};

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.95rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const saveBtnStyle: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
  color: "var(--db-on-accent, #0a0a0a)",
  border: "none",
  borderRadius: "0.5rem",
  padding: "0.7rem 1.25rem",
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.95rem",
  fontWeight: 600,
};

const cancelBtnStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.7rem 1.25rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.95rem",
  cursor: "pointer",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "1.5rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
