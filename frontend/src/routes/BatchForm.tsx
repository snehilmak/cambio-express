import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  createBatch,
  updateBatch,
  useBatch,
  type BatchWriteBody,
} from "../api/batches";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>{isEdit ? "Edit batch" : "New ACH batch"}</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to manage ACH batches.
        </p>
      </main>
    );
  }

  if (isEdit && (detail.isLoading || !detail.data)) {
    return <main style={pageStyle}><p style={emptyStyle}>Loading…</p></main>;
  }

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>
          {isEdit ? `Edit batch #${batchId}` : "New ACH batch"}
        </h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
            fontSize: "0.95rem",
          }}
        >
          Track an ACH withdrawal from a money-transfer company.
        </p>
      </header>

      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      >
        <section style={cardStyle}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))",
              gap: "0.75rem",
            }}
          >
            <Field label="ACH date" highlight={field === "ach_date"}>
              <input type="date" required
                value={form.ach_date}
                onChange={(e) => set("ach_date", e.target.value)}
                style={inputStyle} />
            </Field>
            <Field label="Company">
              <select value={form.company}
                onChange={(e) => set("company", e.target.value)}
                style={inputStyle}>
                {COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Batch ref" highlight={field === "batch_ref"}>
              <input type="text" required
                value={form.batch_ref}
                onChange={(e) => set("batch_ref", e.target.value)}
                style={inputStyle}
                placeholder="From bank statement" />
            </Field>
            <Field label="ACH amount (USD)">
              <input type="number" step="0.01" min="0" required
                value={form.ach_amount}
                onChange={(e) => set("ach_amount", Number(e.target.value))}
                style={inputStyle} />
            </Field>
            <Field label="Status">
              <select value={form.status}
                onChange={(e) => set("status", e.target.value)}
                style={inputStyle}>
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Reconciled">
              <select
                value={form.reconciled ? "yes" : "no"}
                onChange={(e) => set("reconciled", e.target.value === "yes")}
                style={inputStyle}>
                <option value="no">No</option>
                <option value="yes">Yes</option>
              </select>
            </Field>
            <Field label="Transfer dates (optional)">
              <input type="text"
                value={form.transfer_dates}
                onChange={(e) => set("transfer_dates", e.target.value)}
                style={inputStyle}
                placeholder="e.g. 2026-03-10..14" />
            </Field>
          </div>
          <Field label="Notes (optional)">
            <textarea
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              rows={3}
              style={{ ...inputStyle, resize: "vertical", minHeight: "5rem" }}
            />
          </Field>
        </section>

        {error && (
          <p
            role="alert"
            style={{
              ...emptyStyle,
              color: "var(--db-negative, #ff3b30)",
            }}
          >
            {error}
          </p>
        )}

        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <Link to="/batches" style={cancelBtnStyle}>Cancel</Link>
          <button
            type="submit"
            disabled={busy || !form.batch_ref || !form.ach_date}
            style={{
              ...saveBtnStyle,
              opacity: busy || !form.batch_ref || !form.ach_date ? 0.6 : 1,
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {busy ? "Saving…" : isEdit ? "Save changes" : "Create batch"}
          </button>
        </div>
      </form>
    </main>
  );
}

function Field({
  label, highlight, children,
}: {
  label: string;
  highlight?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <span
        style={{
          fontSize: "0.78rem",
          color: highlight
            ? "var(--db-negative, #ff3b30)"
            : "var(--db-text-muted, #a3a3a3)",
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

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem 1.5rem",
  display: "flex",
  flexDirection: "column",
  gap: "0.75rem",
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
  textDecoration: "none",
  display: "inline-flex",
  alignItems: "center",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "1.5rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
