import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  createInvoice, lookupItemByCode, updateInvoice, useInvoice,
  useVendors,
  type InvoiceDetail, type InvoiceWrite,
} from "../api/catalog";
import { ApiError } from "../lib/api";
import { fmtMoney2 } from "../lib/formatters";
import {
  Alert, Breadcrumbs, Button, Card, Checkbox, DateInput, ErrorState,
  Field, InfoTip, Input, Loading, PageHeader, PageShell, Section,
  Select, Textarea, useToast,
} from "../components/ui";
import styles from "./PurchaseInvoices.module.css";

// /app/purchase-invoices/new + /purchase-invoices/:id — key one
// vendor invoice, optionally line-by-line. Lines resolve to
// price-book items by scan code (type or scan the code, blur to
// look it up) so "update price book costs" can flow the invoice's
// unit costs back into the catalog.

function localToday(): string {
  return new Date().toLocaleDateString("en-CA");
}

interface LineDraft {
  itemId: number | null;
  itemName: string;
  code: string;
  codeStatus: "" | "ok" | "missing";
  description: string;
  quantity: string;
  unitCost: string;
  lineTotal: string;   // "" = derive from qty × cost
}

const EMPTY_LINE: LineDraft = {
  itemId: null, itemName: "", code: "", codeStatus: "",
  description: "", quantity: "1", unitCost: "", lineTotal: "",
};

function lineFromDetail(line: InvoiceDetail["lines"][number]): LineDraft {
  return {
    itemId: line.item_id,
    itemName: line.item_name,
    code: "",
    codeStatus: line.item_id != null ? "ok" : "",
    description: line.description,
    quantity: String(line.quantity),
    unitCost: String(line.unit_cost),
    lineTotal: String(line.line_total),
  };
}

export default function PurchaseInvoiceForm() {
  const params = useParams();
  const id = params.id != null ? Number(params.id) : null;
  const existing = useInvoice(id);

  if (id != null && existing.isLoading) {
    return (
      <PageShell maxWidth="64rem">
        <Loading />
      </PageShell>
    );
  }
  if (id != null && (existing.isError || !existing.data)) {
    return (
      <PageShell maxWidth="64rem">
        <ErrorState
          message="Could not load the invoice."
          onRetry={() => { void existing.refetch(); }}
        />
      </PageShell>
    );
  }
  return (
    <InvoiceForm
      key={id ?? "new"}
      invoiceId={id}
      existing={existing.data?.invoice ?? null}
    />
  );
}

function InvoiceForm({
  invoiceId, existing,
}: {
  invoiceId: number | null;
  existing: InvoiceDetail | null;
}) {
  const vendors = useVendors();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();

  const [vendorId, setVendorId] = useState(
    existing != null ? String(existing.vendor_id) : "",
  );
  const [number, setNumber] = useState(existing?.invoice_number ?? "");
  const [invoiceDate, setInvoiceDate] = useState(
    existing?.invoice_date ?? localToday(),
  );
  const [dueDate, setDueDate] = useState(existing?.due_date ?? "");
  const [subtotal, setSubtotal] = useState(
    existing != null && existing.subtotal > 0
      ? String(existing.subtotal) : "",
  );
  const [tax, setTax] = useState(
    existing != null && existing.tax > 0 ? String(existing.tax) : "",
  );
  const [other, setOther] = useState(
    existing != null && existing.other > 0 ? String(existing.other) : "",
  );
  const [status, setStatus] = useState(existing?.status ?? "open");
  const [paidOn, setPaidOn] = useState(existing?.paid_on ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [lines, setLines] = useState<LineDraft[]>(
    existing != null ? existing.lines.map(lineFromDetail) : [],
  );
  const [updateCosts, setUpdateCosts] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function patchLine(index: number, patch: Partial<LineDraft>) {
    setLines((prev) =>
      prev.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    );
  }

  async function resolveCode(index: number, code: string) {
    const trimmed = code.trim();
    if (!trimmed) {
      patchLine(index, { itemId: null, itemName: "", codeStatus: "" });
      return;
    }
    try {
      const item = await lookupItemByCode(trimmed);
      if (item == null) {
        patchLine(index, {
          itemId: null, itemName: "", codeStatus: "missing",
        });
        return;
      }
      setLines((prev) =>
        prev.map((line, i) =>
          i === index
            ? {
                ...line,
                itemId: item.id,
                itemName: item.name,
                codeStatus: "ok",
                description: line.description || item.name,
              }
            : line,
        ),
      );
    } catch {
      patchLine(index, { itemId: null, itemName: "", codeStatus: "missing" });
    }
  }

  const linesTotal = lines.reduce((sum, line) => {
    const keyed = Number.parseFloat(line.lineTotal);
    if (!Number.isNaN(keyed)) return sum + keyed;
    const qty = Number.parseFloat(line.quantity) || 0;
    const cost = Number.parseFloat(line.unitCost) || 0;
    return sum + qty * cost;
  }, 0);
  const invoiceTotal =
    (Number.parseFloat(subtotal) || 0)
    + (Number.parseFloat(tax) || 0)
    + (Number.parseFloat(other) || 0);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body: InvoiceWrite = {
      vendor_id: Number(vendorId),
      invoice_number: number.trim(),
      invoice_date: invoiceDate,
      due_date: dueDate || null,
      subtotal: Number.parseFloat(subtotal) || 0,
      tax: Number.parseFloat(tax) || 0,
      other: Number.parseFloat(other) || 0,
      status,
      paid_on: status === "paid" && paidOn ? paidOn : null,
      notes: notes.trim(),
      update_item_costs: updateCosts,
      lines: lines
        .filter((line) =>
          line.itemId != null || line.description.trim()
          || Number.parseFloat(line.unitCost) > 0)
        .map((line) => ({
          item_id: line.itemId,
          description: line.description.trim(),
          quantity: Number.parseFloat(line.quantity) || 1,
          unit_cost: Number.parseFloat(line.unitCost) || 0,
          line_total: line.lineTotal.trim() === ""
            ? null : Number.parseFloat(line.lineTotal) || 0,
        })),
    };
    try {
      const result = invoiceId == null
        ? await createInvoice(body)
        : await updateInvoice(invoiceId, body);
      void qc.invalidateQueries({ queryKey: ["catalog"] });
      toast({
        message: result.items_cost_updated > 0
          ? `Invoice saved — ${result.items_cost_updated} price-book cost(s) updated.`
          : "Invoice saved.",
        tone: "success",
      });
      navigate("/purchase-invoices");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell maxWidth="64rem">
      <Breadcrumbs
        crumbs={[
          { label: "Purchases", to: "/purchase-invoices" },
          { label: invoiceId == null ? "New invoice" : "Edit invoice" },
        ]}
      />
      <PageHeader
        title={invoiceId == null ? "New purchase invoice" : "Edit invoice"}
        subtitle="Key the paper invoice as printed."
      />
      <form onSubmit={onSubmit}>
        <Card>
          <Section title="Invoice">
            {error && <Alert tone="error">{error}</Alert>}
            <div className={styles.formGrid}>
              <Field label="Vendor">
                <Select
                  value={vendorId} required
                  onChange={(e) => setVendorId(e.target.value)}
                >
                  <option value="" disabled>Pick a vendor…</option>
                  {(vendors.data?.vendors ?? []).map((v) => (
                    <option key={v.id} value={v.id}>{v.name}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Invoice #">
                <Input
                  type="text" value={number} required maxLength={60}
                  onChange={(e) => setNumber(e.target.value)}
                />
              </Field>
              <Field label="Invoice date">
                <DateInput
                  value={invoiceDate} required
                  onChange={(e) => setInvoiceDate(e.target.value)}
                />
              </Field>
              <Field label="Due date (optional)">
                <DateInput
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                />
              </Field>
              <Field label="Merchandise subtotal">
                <Input
                  type="number" min={0} step="0.01" value={subtotal}
                  onChange={(e) => setSubtotal(e.target.value)}
                />
              </Field>
              <Field label="Tax">
                <Input
                  type="number" min={0} step="0.01" value={tax}
                  onChange={(e) => setTax(e.target.value)}
                />
              </Field>
              <Field
                label={
                  <>
                    Other charges
                    <InfoTip text="Freight, deposits, CRV — anything on the paper that isn't merchandise or tax." />
                  </>
                }
              >
                <Input
                  type="number" min={0} step="0.01" value={other}
                  onChange={(e) => setOther(e.target.value)}
                />
              </Field>
              <Field label="Status">
                <Select
                  value={status}
                  onChange={(e) => {
                    setStatus(e.target.value);
                    if (e.target.value === "paid" && !paidOn) {
                      setPaidOn(localToday());
                    }
                  }}
                >
                  <option value="open">Open</option>
                  <option value="paid">Paid</option>
                </Select>
              </Field>
              {status === "paid" && (
                <Field label="Paid on">
                  <DateInput
                    value={paidOn}
                    onChange={(e) => setPaidOn(e.target.value)}
                  />
                </Field>
              )}
            </div>
            <Field label="Notes (optional)">
              <Textarea
                value={notes} maxLength={500} rows={2}
                onChange={(e) => setNotes(e.target.value)}
              />
            </Field>
          </Section>
        </Card>
        <Card>
          <Section
            title="Line items (optional)"
            actions={
              <Button
                size="sm" tone="secondary" type="button"
                onClick={() => setLines((prev) => [...prev, EMPTY_LINE])}
              >
                + Add line
              </Button>
            }
          >
            <p>
              Type or scan an item&apos;s code to link it to the price
              book — linked lines can update your catalog costs on
              save. Leave the code blank for one-off charges.
            </p>
            {lines.map((line, i) => (
              <div key={i} className={styles.lineRow}>
                <Field label={i === 0 ? "Scan code" : ""}>
                  <Input
                    type="text" value={line.code} maxLength={30}
                    placeholder="Optional"
                    onChange={(e) => patchLine(i, { code: e.target.value })}
                    onBlur={(e) => { void resolveCode(i, e.target.value); }}
                  />
                  <span className={styles.lineMeta}>
                    {line.codeStatus === "ok" && (line.itemName || "linked")}
                    {line.codeStatus === "missing" && "No item with that code"}
                  </span>
                </Field>
                <Field label={i === 0 ? "Description" : ""}>
                  <Input
                    type="text" value={line.description} maxLength={160}
                    onChange={(e) =>
                      patchLine(i, { description: e.target.value })
                    }
                  />
                </Field>
                <Field label={i === 0 ? "Qty" : ""}>
                  <Input
                    type="number" min={0} step="any" value={line.quantity}
                    onChange={(e) =>
                      patchLine(i, { quantity: e.target.value })
                    }
                  />
                </Field>
                <Field label={i === 0 ? "Unit cost" : ""}>
                  <Input
                    type="number" min={0} step="0.01" value={line.unitCost}
                    onChange={(e) =>
                      patchLine(i, { unitCost: e.target.value })
                    }
                  />
                </Field>
                <Field label={i === 0 ? "Line total" : ""}>
                  <Input
                    type="number" min={0} step="0.01" value={line.lineTotal}
                    placeholder="auto"
                    onChange={(e) =>
                      patchLine(i, { lineTotal: e.target.value })
                    }
                  />
                </Field>
                <Field label={i === 0 ? " " : ""}>
                  <Button
                    size="sm" tone="danger" type="button"
                    onClick={() =>
                      setLines((prev) => prev.filter((_, j) => j !== i))
                    }
                  >
                    Remove
                  </Button>
                </Field>
              </div>
            ))}
            <div className={styles.totalsRow}>
              {lines.length > 0 && (
                <span>
                  <span className={styles.totalLabel}>Lines: </span>
                  {fmtMoney2(linesTotal)}
                </span>
              )}
              <span>
                <span className={styles.totalLabel}>Invoice total: </span>
                {fmtMoney2(invoiceTotal)}
              </span>
            </div>
            <Checkbox
              checked={updateCosts}
              onChange={(next) => setUpdateCosts(next)}
            >
              Update price-book costs from linked lines
            </Checkbox>
          </Section>
        </Card>
        <div className={styles.formActions}>
          <Button
            tone="secondary" type="button"
            onClick={() => navigate("/purchase-invoices")}
          >
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={busy}>
            {invoiceId == null ? "Add invoice" : "Save changes"}
          </Button>
        </div>
      </form>
    </PageShell>
  );
}
