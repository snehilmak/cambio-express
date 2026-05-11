import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  BANK_CATEGORY_OPTIONS,
  createRule,
  deleteRule,
  toggleRule,
  updateRule,
  useBankAccounts,
  useBankRules,
  type BankRuleRow,
  type BankRuleWriteBody,
} from "../api/bankSync";
import { ApiError } from "../lib/api";
import {
  Card, EmptyState, ErrorState, Loading, PageHeader, PageShell, Section,
  tokens,
} from "../components/ui";

// /app/bank/rules — bank reconcile rules CRUD. The legacy
// /bank/rules Jinja page rendered the same list + create form;
// this is a tighter version backed by /api/v2/bank/rules.

const SIGN_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "any",    label: "Any sign" },
  { value: "credit", label: "Credit (+)" },
  { value: "debit",  label: "Debit (-)" },
];

const MATCH_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "contains",      label: "Contains" },
  { value: "starts_with",   label: "Starts with" },
  { value: "ends_with",     label: "Ends with" },
  { value: "exact",         label: "Exact match" },
  { value: "regex",         label: "Regex" },
];

interface FormState {
  enabled: boolean;
  priority: number;
  desc_match_type: string;
  desc_match_value: string;
  sign_filter: string;
  amount_min: string;
  amount_max: string;
  account_filter_id: string;
  target_kind: string;
  auto_post: boolean;
  description: string;
}

const EMPTY_FORM: FormState = {
  enabled: true,
  priority: 100,
  desc_match_type: "contains",
  desc_match_value: "",
  sign_filter: "any",
  amount_min: "",
  amount_max: "",
  account_filter_id: "",
  target_kind: "cash_expense",
  auto_post: false,
  description: "",
};

export default function BankRules() {
  const rules = useBankRules();
  const accounts = useBankAccounts();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function bodyFromForm(): BankRuleWriteBody {
    return {
      enabled: form.enabled,
      priority: Number(form.priority) || 100,
      desc_match_type: form.desc_match_type,
      desc_match_value: form.desc_match_value,
      sign_filter: form.sign_filter,
      amount_min_cents: form.amount_min
        ? Math.round(Number(form.amount_min) * 100)
        : null,
      amount_max_cents: form.amount_max
        ? Math.round(Number(form.amount_max) * 100)
        : null,
      account_filter_id: form.account_filter_id
        ? Number(form.account_filter_id)
        : null,
      target_kind: form.target_kind,
      auto_post: form.auto_post,
      description: form.description,
    };
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = bodyFromForm();
      if (editingId) {
        await updateRule(editingId, body);
      } else {
        await createRule(body);
      }
      setForm(EMPTY_FORM);
      setEditingId(null);
      await rules.refetch();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(r: BankRuleRow) {
    setEditingId(r.id);
    setForm({
      enabled: r.enabled,
      priority: r.priority,
      desc_match_type: r.desc_match_type,
      desc_match_value: r.desc_match_value,
      sign_filter: r.sign_filter,
      amount_min: r.amount_min_cents != null ? (r.amount_min_cents / 100).toString() : "",
      amount_max: r.amount_max_cents != null ? (r.amount_max_cents / 100).toString() : "",
      account_filter_id: r.account_filter_id != null ? String(r.account_filter_id) : "",
      target_kind: r.target_kind,
      auto_post: r.auto_post,
      description: r.description,
    });
  }

  async function handleToggle(r: BankRuleRow) {
    await toggleRule(r.id, !r.enabled);
    await rules.refetch();
  }

  async function handleDelete(r: BankRuleRow) {
    if (!confirm(`Delete rule "${r.description || r.desc_match_value}"?`)) return;
    await deleteRule(r.id);
    await rules.refetch();
  }

  return (
    <PageShell maxWidth="70rem" gap="1.25rem">
      <PageHeader
        title="Bank Rules"
        actions={(
          <Link to="/bank-transactions" style={btnOutlineLink}>← Transactions</Link>
        )}
      />

      {error && <ErrorState message={error} />}

      <Section title={editingId ? "Edit rule" : "Create new rule"}>
        <Card>
          <form onSubmit={handleSubmit} style={formGrid}>
          <FormField label="Match type" span={1}>
            <select
              value={form.desc_match_type}
              onChange={(e) => setForm({ ...form, desc_match_type: e.target.value })}
              style={inputStyle}
            >
              {MATCH_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </FormField>
          <FormField label="Match value" span={1}>
            <input
              required
              value={form.desc_match_value}
              onChange={(e) => setForm({ ...form, desc_match_value: e.target.value })}
              placeholder="e.g. REMOTE DEPOSIT FEE"
              style={inputStyle}
            />
          </FormField>
          <FormField label="Sign filter" span={1}>
            <select
              value={form.sign_filter}
              onChange={(e) => setForm({ ...form, sign_filter: e.target.value })}
              style={inputStyle}
            >
              {SIGN_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </FormField>
          <FormField label="Account filter (optional)" span={1}>
            <select
              value={form.account_filter_id}
              onChange={(e) => setForm({ ...form, account_filter_id: e.target.value })}
              style={inputStyle}
            >
              <option value="">Any account</option>
              {(accounts.data?.rows ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}{a.last4 ? ` ••${a.last4}` : ""}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Min amount $" span={1}>
            <input
              type="number"
              step="0.01"
              value={form.amount_min}
              onChange={(e) => setForm({ ...form, amount_min: e.target.value })}
              placeholder="(blank = no min)"
              style={inputStyle}
            />
          </FormField>
          <FormField label="Max amount $" span={1}>
            <input
              type="number"
              step="0.01"
              value={form.amount_max}
              onChange={(e) => setForm({ ...form, amount_max: e.target.value })}
              placeholder="(blank = no max)"
              style={inputStyle}
            />
          </FormField>
          <FormField label="Target category" span={1}>
            <select
              value={form.target_kind}
              onChange={(e) => setForm({ ...form, target_kind: e.target.value })}
              style={inputStyle}
            >
              {BANK_CATEGORY_OPTIONS.map((o) => (
                <option key={o.slug} value={o.slug}>{o.label}</option>
              ))}
            </select>
          </FormField>
          <FormField label="Priority" span={1}>
            <input
              type="number"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
              style={inputStyle}
            />
          </FormField>
          <FormField label="Description (memo)" span={2}>
            <input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="What this rule does"
              style={inputStyle}
            />
          </FormField>
          <label style={{ ...checkRow }}>
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            />
            Enabled
          </label>
          <label style={checkRow}>
            <input
              type="checkbox"
              checked={form.auto_post}
              onChange={(e) => setForm({ ...form, auto_post: e.target.checked })}
            />
            Auto-post matching transactions to daily book
          </label>
          <div style={{ gridColumn: "span 2", display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
            <button type="submit" disabled={busy} style={btnPrimary}>
              {editingId ? (busy ? "Saving…" : "Save changes") : (busy ? "Creating…" : "Create rule")}
            </button>
            {editingId && (
              <button
                type="button"
                style={btnOutline}
                onClick={() => {
                  setEditingId(null);
                  setForm(EMPTY_FORM);
                }}
              >
                Cancel
              </button>
            )}
          </div>
          </form>
        </Card>
      </Section>

      <Section
        title={`Your rules`}
        actions={<span style={muted}>({rules.data?.total ?? 0})</span>}
      >
        <Card>
          {rules.isLoading && <Loading />}
          {!rules.isLoading && (rules.data?.rows ?? []).length === 0 && (
            <EmptyState title="No rules yet" body="Create one above to start auto-categorising bank transactions." />
          )}
          {(rules.data?.rows ?? []).length > 0 && (
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={thStyle}>Description</th>
                  <th style={thStyle}>Match</th>
                  <th style={thStyle}>Sign</th>
                  <th style={thStyle}>Account</th>
                  <th style={thStyle}>Category</th>
                  <th style={thStyle}>Hits</th>
                  <th style={thStyle}></th>
                </tr>
              </thead>
              <tbody>
                {(rules.data?.rows ?? []).map((r) => (
                  <tr key={r.id} style={!r.enabled ? { opacity: 0.5 } : undefined}>
                    <td style={tdStyle}>{r.description || "—"}</td>
                    <td style={tdStyle}>
                      <code>{r.desc_match_type}</code>: {r.desc_match_value}
                    </td>
                    <td style={tdStyle}>{r.sign_filter}</td>
                    <td style={tdStyle}>{r.account_filter_label || "Any"}</td>
                    <td style={tdStyle}>{r.target_kind}</td>
                    <td style={tdStyle}>{r.match_count}</td>
                    <td style={{ ...tdStyle, textAlign: "right", whiteSpace: "nowrap" }}>
                      <button type="button" style={btnOutlineSm} onClick={() => startEdit(r)}>
                        Edit
                      </button>{" "}
                      <button type="button" style={btnOutlineSm} onClick={() => handleToggle(r)}>
                        {r.enabled ? "Disable" : "Enable"}
                      </button>{" "}
                      <button type="button" style={btnDangerSm} onClick={() => handleDelete(r)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </Section>
    </PageShell>
  );
}

function FormField({ label, span, children }: { label: string; span: 1 | 2; children: React.ReactNode }) {
  return (
    <label style={{ gridColumn: span === 2 ? "span 2" : undefined }}>
      <div style={fieldLabel}>{label}</div>
      {children}
    </label>
  );
}

const formGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: "0.75rem 1rem",
};
const fieldLabel: React.CSSProperties = {
  fontSize: "0.7rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: tokens.textMuted,
  fontWeight: 600,
  marginBottom: "0.25rem",
};
const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "0.5rem 0.65rem",
  background: tokens.surface,
  color: "inherit",
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.4rem",
  fontSize: "0.85rem",
  fontFamily: "inherit",
};
const checkRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  fontSize: "0.85rem",
};
const muted: React.CSSProperties = {
  color: tokens.textMuted,
  fontSize: "0.85rem",
};
const btnPrimary: React.CSSProperties = {
  background: tokens.accent,
  color: "#000",
  border: "none",
  padding: "0.5rem 1rem",
  borderRadius: "0.5rem",
  fontWeight: 600,
  fontSize: "0.85rem",
  cursor: "pointer",
};
const btnOutline: React.CSSProperties = {
  background: "transparent",
  color: "inherit",
  border: `1px solid ${tokens.border}`,
  padding: "0.5rem 1rem",
  borderRadius: "0.5rem",
  fontSize: "0.85rem",
  cursor: "pointer",
};
const btnOutlineLink: React.CSSProperties = {
  ...btnOutline,
  textDecoration: "none",
  display: "inline-block",
};
const btnOutlineSm: React.CSSProperties = {
  ...btnOutline,
  padding: "0.25rem 0.6rem",
  fontSize: "0.75rem",
};
const btnDangerSm: React.CSSProperties = {
  ...btnOutlineSm,
  color: tokens.negative,
  borderColor: tokens.negative,
};
const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "0.85rem",
};
const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.5rem 0.75rem",
  borderBottom: `1px solid ${tokens.border}`,
  fontSize: "0.7rem",
  textTransform: "uppercase",
  color: tokens.textMuted,
  fontWeight: 500,
};
const tdStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};
