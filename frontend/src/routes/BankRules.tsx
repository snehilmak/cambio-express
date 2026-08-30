import { useState, type FormEvent } from "react";

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
  Breadcrumbs,
  Button, Card, Checkbox, ConfirmDialog, EmptyState, ErrorState,
  Field, Input, Loading, PageHeader, PageShell, RowActions, Section,
  Select, Table, tdStyle, thStyle, useToast,
} from "../components/ui";
import styles from "./BankRules.module.css";

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

const SPAN_2 = { gridColumn: "span 2" } as const;

export default function BankRules() {
  const rules = useBankRules();
  const accounts = useBankAccounts();
  const toast = useToast();
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
      const wasEdit = !!editingId;
      setForm(EMPTY_FORM);
      setEditingId(null);
      await rules.refetch();
      toast({ message: wasEdit ? "Rule updated." : "Rule created.", tone: "success" });
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
    toast({ message: r.enabled ? "Rule disabled." : "Rule enabled.", tone: "success" });
  }

  // Destructive: gate via ConfirmDialog rather than window.confirm
  // so the prompt is themed + accessible.  `pendingDelete` is the
  // row being staged for removal; null means "no dialog showing".
  const [pendingDelete, setPendingDelete] = useState<BankRuleRow | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  async function doDelete() {
    if (!pendingDelete) return;
    setDeleteBusy(true);
    try {
      await deleteRule(pendingDelete.id);
      await rules.refetch();
      setPendingDelete(null);
      toast({ message: "Rule deleted.", tone: "success" });
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <PageShell gap="1.25rem">

      <Breadcrumbs crumbs={[{ label: "Finance" }, { label: "Bank rules" }]} />

      <PageHeader
        title="Bank Rules"
        subtitle="Auto-categorize incoming bank transactions by description pattern."
      />

      {error && <ErrorState message={error} />}

      <Section title={editingId ? "Edit rule" : "Create new rule"}>
        <Card>
          <form onSubmit={handleSubmit} className={styles.formGrid}>
            <Field label="Match type">
              <Select
                value={form.desc_match_type}
                onChange={(e) => setForm({ ...form, desc_match_type: e.target.value })}
              >
                {MATCH_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="Match value">
              <Input
                required
                value={form.desc_match_value}
                onChange={(e) => setForm({ ...form, desc_match_value: e.target.value })}
                placeholder="e.g. REMOTE DEPOSIT FEE"
              />
            </Field>
            <Field label="Sign filter">
              <Select
                value={form.sign_filter}
                onChange={(e) => setForm({ ...form, sign_filter: e.target.value })}
              >
                {SIGN_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="Account filter (optional)">
              <Select
                value={form.account_filter_id}
                onChange={(e) => setForm({ ...form, account_filter_id: e.target.value })}
              >
                <option value="">Any account</option>
                {(accounts.data?.rows ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}{a.last4 ? ` ••${a.last4}` : ""}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Min amount $">
              <Input
                type="number"
                step="0.01"
                value={form.amount_min}
                onChange={(e) => setForm({ ...form, amount_min: e.target.value })}
                placeholder="(blank = no min)"
              />
            </Field>
            <Field label="Max amount $">
              <Input
                type="number"
                step="0.01"
                value={form.amount_max}
                onChange={(e) => setForm({ ...form, amount_max: e.target.value })}
                placeholder="(blank = no max)"
              />
            </Field>
            <Field label="Target category">
              <Select
                value={form.target_kind}
                onChange={(e) => setForm({ ...form, target_kind: e.target.value })}
              >
                {BANK_CATEGORY_OPTIONS.map((o) => (
                  <option key={o.slug} value={o.slug}>{o.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="Priority">
              <Input
                type="number"
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
              />
            </Field>
            <Field label="Description (memo)" style={SPAN_2}>
              <Input
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="What this rule does"
              />
            </Field>
            <Checkbox
              checked={form.enabled}
              onChange={(v) => setForm({ ...form, enabled: v })}
            >
              Enabled
            </Checkbox>
            <Checkbox
              checked={form.auto_post}
              onChange={(v) => setForm({ ...form, auto_post: v })}
            >
              Auto-post matching transactions to daily book
            </Checkbox>
            <div className={styles.formActions}>
              <Button type="submit" busy={busy} disabled={busy}>
                {editingId ? (busy ? "Saving…" : "Save changes") : (busy ? "Creating…" : "Create rule")}
              </Button>
              {editingId && (
                <Button
                  type="button"
                  tone="secondary"
                  onClick={() => {
                    setEditingId(null);
                    setForm(EMPTY_FORM);
                  }}
                >
                  Cancel
                </Button>
              )}
            </div>
          </form>
        </Card>
      </Section>

      <Section
        title="Your rules"
        actions={<span className={styles.muted}>({rules.data?.total ?? 0})</span>}
      >
        <Card>
          {rules.isLoading && <Loading />}
          {!rules.isLoading && (rules.data?.rows ?? []).length === 0 && (
            <EmptyState title="No rules yet" body="Create one above to start auto-categorising bank transactions." />
          )}
          {(rules.data?.rows ?? []).length > 0 && (
            <Table>
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
                  <tr key={r.id} className={!r.enabled ? styles.rowDisabled : undefined}>
                    <td style={tdStyle}>{r.description || "—"}</td>
                    <td style={tdStyle}>
                      <code>{r.desc_match_type}</code>: {r.desc_match_value}
                    </td>
                    <td style={tdStyle}>{r.sign_filter}</td>
                    <td style={tdStyle}>{r.account_filter_label || "Any"}</td>
                    <td style={tdStyle}>{r.target_kind}</td>
                    <td style={tdStyle}>{r.match_count}</td>
                    <td style={tdStyle} className={styles.actionsCell}>
                      <RowActions
                        title={r.description || r.desc_match_value || "Rule"}
                        actions={[
                          { label: "Edit", onClick: () => startEdit(r) },
                          {
                            label: r.enabled ? "Disable" : "Enable",
                            onClick: () => handleToggle(r),
                          },
                          {
                            label: "Delete", tone: "danger",
                            onClick: () => setPendingDelete(r),
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
      </Section>

      <ConfirmDialog
        open={pendingDelete != null}
        title="Delete rule"
        message={
          `Delete rule "${pendingDelete?.description || pendingDelete?.desc_match_value || ""}"? `
          + "Existing tagged transactions keep their labels; only "
          + "future syncs stop applying this rule."
        }
        confirmLabel="Delete"
        confirmTone="danger"
        busy={deleteBusy}
        onConfirm={() => { void doDelete(); }}
        onCancel={() => setPendingDelete(null)}
      />
    </PageShell>
  );
}
