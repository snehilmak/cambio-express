import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  createReturnCheck,
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
import { EmptyState, Loading } from "../components/ui";

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>
          {isEdit ? "Edit return check" : "New return check"}
        </h1>
        <p style={emptyStyle}>
          Sign in as a store admin to manage return checks.
        </p>
      </main>
    );
  }

  if (isEdit && (detail.isLoading || !detail.data)) {
    return <main style={pageStyle}><Loading /></main>;
  }

  const status = isEdit ? detail.data?.return_check.status ?? "pending" : "pending";
  const recovered = isEdit ? detail.data?.return_check.recovered_total ?? 0 : 0;

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>
          {isEdit ? `Return check #${rcId}` : "New return check"}
        </h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
            fontSize: "0.95rem",
          }}
        >
          Track a bounced check from a customer and any partial recovery.
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
            <Field label="Bounced on" highlight={field === "bounced_on"}>
              <input type="date" required
                value={form.bounced_on}
                onChange={(e) => set("bounced_on", e.target.value)}
                style={inputStyle} />
            </Field>
            <Field label="Customer name" highlight={field === "customer_name"}>
              <input type="text" required
                value={form.customer_name}
                onChange={(e) => set("customer_name", e.target.value)}
                style={inputStyle} />
            </Field>
            <Field label="Check number">
              <input type="text"
                value={form.check_number ?? ""}
                onChange={(e) => set("check_number", e.target.value)}
                style={inputStyle} />
            </Field>
            <Field label="Payer bank">
              <input type="text"
                value={form.payer_bank ?? ""}
                onChange={(e) => set("payer_bank", e.target.value)}
                style={inputStyle} />
            </Field>
            <Field label="Amount (USD)" highlight={field === "amount"}>
              <input type="number" step="0.01" min="0.01" required
                value={form.amount}
                onChange={(e) => set("amount", Number(e.target.value))}
                style={inputStyle} />
            </Field>
          </div>
          <Field label="Notes (optional)">
            <textarea
              value={form.notes ?? ""}
              onChange={(e) => set("notes", e.target.value)}
              rows={3}
              style={{ ...inputStyle, resize: "vertical", minHeight: "5rem" }}
            />
          </Field>
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
          <Link to="/return-checks" style={cancelBtnStyle}>Cancel</Link>
          <button
            type="submit"
            disabled={busy || !form.customer_name || !form.bounced_on}
            style={{
              ...saveBtnStyle,
              opacity:
                busy || !form.customer_name || !form.bounced_on ? 0.6 : 1,
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {busy ? "Saving…" : isEdit ? "Save changes" : "Create return check"}
          </button>
        </div>
      </form>

      {isEdit && (
        <section style={{ ...cardStyle, marginTop: "1rem" }}>
          <h2 style={sectionTitle}>Status</h2>
          <p
            style={{
              margin: "0.35rem 0 0.75rem",
              color: "var(--db-text-muted, #a3a3a3)",
              fontSize: "0.9rem",
            }}
          >
            Current: <strong style={{ textTransform: "capitalize" }}>{status}</strong>
            {" · "}Recovered <span style={mono}>${recovered.toFixed(2)}</span>
            {" of "}<span style={mono}>${form.amount.toFixed(2)}</span>
          </p>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            {status === "pending" && (
              <>
                <button
                  type="button"
                  onClick={() => transition(markLoss, "Mark loss")}
                  disabled={busy}
                  style={dangerBtn}
                >
                  Mark loss
                </button>
                <button
                  type="button"
                  onClick={() => transition(markFraud, "Mark fraud")}
                  disabled={busy}
                  style={dangerBtn}
                >
                  Mark fraud
                </button>
              </>
            )}
            {status !== "pending" && (
              <button
                type="button"
                onClick={() => transition(reopenReturnCheck, "Reopen")}
                disabled={busy}
                style={secondaryBtn}
              >
                Reopen
              </button>
            )}
          </div>
        </section>
      )}

      {isEdit && (
        <section style={{ ...cardStyle, marginTop: "1rem" }}>
          <h2 style={sectionTitle}>Recovery payments</h2>
          {payments.isLoading && <Loading />}
          {payments.data && payments.data.payments.length === 0 && (
            <EmptyState title="No recovery payments recorded." />
          )}
          {payments.data && payments.data.payments.length > 0 && (
            <PaymentsTable rows={payments.data.payments} />
          )}
        </section>
      )}
    </main>
  );
}

function PaymentsTable({ rows }: { rows: ReturnCheckPaymentRow[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.92rem",
        }}
      >
        <thead>
          <tr>
            {["Paid on", "Amount", "Method", "Notes"].map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: i === 1 ? "right" : "left",
                  padding: "0.6rem 0.75rem",
                  color: "var(--db-text-muted, #a3a3a3)",
                  fontWeight: 500,
                  fontSize: "0.78rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  borderBottom: "1px solid var(--db-border, #262626)",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td style={cellStyle}>
                <span style={monoMuted}>{p.paid_on}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${p.amount.toFixed(2)}</span>
              </td>
              <td style={cellStyle}>{p.method || "—"}</td>
              <td style={cellStyle}>{p.notes || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

const sectionTitle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "1.1rem",
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

const dangerBtn: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-negative, #ff3b30)",
  border: "1px solid var(--db-negative, #ff3b30)",
  borderRadius: "0.5rem",
  padding: "0.55rem 1rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.9rem",
  fontWeight: 600,
  cursor: "pointer",
};

const secondaryBtn: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 1rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.9rem",
  cursor: "pointer",
};

const mono: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const monoMuted: React.CSSProperties = {
  ...mono,
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
};

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "1.5rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
