import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  updateTransfer,
  useTransfer,
  type CreateTransferBody,
} from "../api/transfers";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

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

  const [form, setForm] = useState<CreateTransferBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hydrate the form once the existing transfer arrives. Edits
  // happen on the form copy — only a successful PUT writes back.
  useEffect(() => {
    if (!detail.data) return;
    const t = detail.data.transfer;
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
      <main style={pageStyle}>
        <h1 style={titleStyle}>Edit transfer</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to edit transfers.
        </p>
      </main>
    );
  }

  if (!Number.isFinite(transferId)) {
    return (
      <main style={pageStyle}>
        <p style={emptyStyle}>Invalid transfer ID.</p>
      </main>
    );
  }

  if (detail.isLoading || form == null) {
    return (
      <main style={pageStyle}>
        <p style={emptyStyle}>Loading…</p>
      </main>
    );
  }

  if (detail.isError) {
    return (
      <main style={pageStyle}>
        <p style={{ ...emptyStyle, color: "var(--db-negative, #ff3b30)" }}>
          {detail.error instanceof Error
            ? detail.error.message
            : "Could not load this transfer."}
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>Edit transfer #{transferId}</h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
          }}
        >
          Federal tax is recomputed server-side on save.
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
              <input type="date" value={form.send_date}
                onChange={(e) => set("send_date", e.target.value)}
                style={inputStyle} required />
            </Field>
            <Field label="Company">
              <select value={form.company}
                onChange={(e) => set("company", e.target.value)}
                style={inputStyle}>
                {COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Service">
              <select value={form.service_type}
                onChange={(e) => set("service_type", e.target.value)}
                style={inputStyle}>
                {SERVICES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Status">
              <select value={form.status}
                onChange={(e) => set("status", e.target.value)}
                style={inputStyle}>
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
          </Grid>
        </section>

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Sender</h2>
          <Grid>
            <Field label="Full name">
              <input type="text" value={form.sender_name}
                onChange={(e) => set("sender_name", e.target.value)}
                style={inputStyle} required />
            </Field>
            <Field label="Phone country">
              <input type="text" value={form.sender_phone_country}
                onChange={(e) => set("sender_phone_country", e.target.value)}
                style={inputStyle} placeholder="+1" />
            </Field>
            <Field label="Phone">
              <input type="tel" value={form.sender_phone}
                onChange={(e) => set("sender_phone", e.target.value)}
                style={inputStyle} />
            </Field>
            <Field label="Address">
              <input type="text" value={form.sender_address}
                onChange={(e) => set("sender_address", e.target.value)}
                style={inputStyle} />
            </Field>
          </Grid>
        </section>

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Recipient</h2>
          <Grid>
            <Field label="Country">
              <select value={form.country}
                onChange={(e) => set("country", e.target.value)}
                style={inputStyle}>
                {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Recipient name">
              <input type="text" value={form.recipient_name}
                onChange={(e) => set("recipient_name", e.target.value)}
                style={inputStyle} />
            </Field>
            <Field label="Recipient phone">
              <input type="tel" value={form.recipient_phone}
                onChange={(e) => set("recipient_phone", e.target.value)}
                style={inputStyle} />
            </Field>
          </Grid>
        </section>

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Amounts</h2>
          <Grid>
            <Field label="Send amount (USD)">
              <input type="number" step="0.01" min="0"
                value={form.send_amount}
                onChange={(e) => set("send_amount", Number(e.target.value))}
                style={inputStyle} required />
            </Field>
            <Field label="Fee (USD)">
              <input type="number" step="0.01" min="0"
                value={form.fee}
                onChange={(e) => set("fee", Number(e.target.value))}
                style={inputStyle} />
            </Field>
            <Field label="Confirm #">
              <input type="text" value={form.confirm_number}
                onChange={(e) => set("confirm_number", e.target.value)}
                style={inputStyle} />
            </Field>
          </Grid>
        </section>

        <section style={cardStyle}>
          <h2 style={sectionTitleStyle}>Processed by</h2>
          <Grid>
            <Field label="Employee ID">
              <input type="number" min="1"
                value={form.employee_id ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  set("employee_id", v ? Number(v) : null);
                }}
                placeholder="Roster ID"
                style={inputStyle} required />
            </Field>
          </Grid>
          <p style={{
            margin: "0.5rem 0 0",
            fontSize: "0.85rem",
            color: "var(--db-text-muted, #a3a3a3)",
          }}>
            Required: who made this edit. Roster picker dropdown
            lands in the next PR.
          </p>
        </section>

        {error && (
          <p role="alert" style={{ ...emptyStyle, color: "var(--db-negative, #ff3b30)" }}>
            {error}
          </p>
        )}

        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <button type="button"
            onClick={() => navigate(`/transfers/${transferId}`)}
            style={cancelBtnStyle} disabled={busy}>
            Cancel
          </button>
          <button type="submit"
            disabled={busy || !form.sender_name || !form.send_amount || !form.employee_id}
            style={{
              ...saveBtnStyle,
              opacity:
                busy || !form.sender_name || !form.send_amount || !form.employee_id
                  ? 0.6 : 1,
              cursor: busy ? "wait" : "pointer",
            }}>
            {busy ? "Saving…" : "Save changes"}
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
      <span style={{
        fontSize: "0.78rem",
        color: "var(--db-text-muted, #a3a3a3)",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}>
        {label}
      </span>
      {children}
    </label>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))",
      gap: "0.75rem",
    }}>
      {children}
    </div>
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
