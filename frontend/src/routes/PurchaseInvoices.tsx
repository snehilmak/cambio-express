import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import {
  deleteInvoice, updateInvoice, useInvoices, useVendors,
  type InvoiceRow,
} from "../api/catalog";
import { ApiError } from "../lib/api";
import { fmtMoney2 } from "../lib/formatters";
import { hasPermission } from "../lib/permissions";
import { useUrlFilterState } from "../lib/useUrlFilterState";
import {
  Breadcrumbs, ButtonLink, Card, EmptyState, ErrorState, Field,
  InfoTip, Input, Loading, PageHeader, PageShell, Pager, Pill,
  RowActions, Section, Select, Table, tdStyle, thStyle, useToast,
} from "../components/ui";
import styles from "./PurchaseInvoices.module.css";

// /app/purchase-invoices — vendor invoice log (P3-2). Key each
// paper invoice, optionally line-by-line with price-book links so
// costs flow back into the catalog. List here; entry/edit on the
// dedicated form page (lines don't fit a modal).

function localToday(): string {
  return new Date().toLocaleDateString("en-CA");
}

export default function PurchaseInvoices() {
  const canManage = hasPermission("catalog", "update");
  // 300ms debounce + 2-char minimum via the shared URL-filter hook
  // (CLAUDE.md "Table search UX").
  const filters = useUrlFilterState({ q: "", vendor_id: "", status: "" });
  const invoices = useInvoices({
    q: filters.params.q,
    page: filters.page,
    vendorId: filters.params.vendor_id,
    status: filters.params.status,
  });
  const vendors = useVendors();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["catalog", "invoices"] });
  }

  async function togglePaid(inv: InvoiceRow) {
    try {
      await updateInvoice(
        inv.id,
        inv.status === "paid"
          ? { status: "open" }
          : { status: "paid", paid_on: localToday() },
      );
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not update the invoice.",
        tone: "error",
      });
    }
  }

  async function remove(inv: InvoiceRow) {
    try {
      await deleteInvoice(inv.id);
      refresh();
      toast({
        message: `Invoice ${inv.invoice_number} deleted.`,
        tone: "success",
      });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not delete the invoice.",
        tone: "error",
      });
    }
  }

  const data = invoices.data;
  return (
    <PageShell maxWidth="72rem">
      <Breadcrumbs crumbs={[{ label: "Purchases" }]} />
      <PageHeader
        title={
          <>
            Purchase invoices
            <InfoTip text="Key each vendor invoice as it arrives. Link lines to price-book items and their unit costs can update your catalog automatically." />
          </>
        }
        subtitle="What the store bought, from whom, and for how much."
        actions={
          canManage ? (
            <ButtonLink to="/purchase-invoices/new" size="sm">
              + Add invoice
            </ButtonLink>
          ) : undefined
        }
      />
      <Section title="Invoices">
        <div className={styles.filtersRow}>
          <div className={styles.searchField}>
            <Field label="Search">
              <Input
                type="search"
                placeholder="Invoice number…"
                value={filters.draft.q ?? filters.params.q}
                onChange={(e) => filters.debounced("q", e.target.value)}
              />
            </Field>
          </div>
          <Field label="Vendor">
            <Select
              value={filters.params.vendor_id}
              onChange={(e) => filters.setParam("vendor_id", e.target.value)}
            >
              <option value="">All</option>
              {(vendors.data?.vendors ?? []).map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Status">
            <Select
              value={filters.params.status}
              onChange={(e) => filters.setParam("status", e.target.value)}
            >
              <option value="">All</option>
              <option value="open">Open</option>
              <option value="paid">Paid</option>
            </Select>
          </Field>
        </div>
        {invoices.isLoading && <Loading />}
        {invoices.isError && (
          <ErrorState
            message="Could not load invoices."
            onRetry={() => { void invoices.refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && (
          <EmptyState
            title={
              filters.params.q || filters.params.vendor_id
              || filters.params.status
                ? "No invoices match"
                : "No invoices yet"
            }
            body={
              canManage
                ? 'Key your first vendor invoice with "+ Add invoice".'
                : "No invoices on file."
            }
          />
        )}
        {data && data.rows.length > 0 && (
          <>
            <Card>
              <div style={{ overflowX: "auto" }}>
                <Table>
                  <thead>
                    <tr>
                      {["Invoice #", "Vendor", "Date", "Due", "Total",
                        "Lines", "Status",
                        ...(canManage ? ["Actions"] : [])].map((h) => (
                        <th key={h} style={thStyle}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((inv) => (
                      <tr key={inv.id}>
                        <td style={tdStyle}>
                          <span className={styles.mono}>
                            {inv.invoice_number}
                          </span>
                        </td>
                        <td style={tdStyle}>{inv.vendor_name}</td>
                        <td style={tdStyle}>{inv.invoice_date}</td>
                        <td style={tdStyle}>{inv.due_date ?? "—"}</td>
                        <td style={tdStyle}>{fmtMoney2(inv.total)}</td>
                        <td style={tdStyle}>{inv.line_count}</td>
                        <td style={tdStyle}>
                          <Pill
                            tone={inv.status === "paid"
                              ? "success" : "warning"}
                          >
                            {inv.status === "paid"
                              ? `paid ${inv.paid_on ?? ""}`.trim()
                              : "open"}
                          </Pill>
                        </td>
                        {canManage && (
                          <td style={tdStyle}>
                            <RowActions
                              title={inv.invoice_number}
                              actions={[
                                {
                                  label: "Edit",
                                  tone: "primary",
                                  onClick: () =>
                                    navigate(`/purchase-invoices/${inv.id}`),
                                },
                                {
                                  label: inv.status === "paid"
                                    ? "Reopen" : "Mark paid",
                                  tone: "primary",
                                  onClick: () => togglePaid(inv),
                                },
                                {
                                  label: "Delete",
                                  tone: "warning",
                                  onClick: () => remove(inv),
                                },
                              ]}
                            />
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            </Card>
            {data.total_pages > 1 && (
              <Pager
                page={data.page}
                totalPages={data.total_pages}
                onPage={filters.setPage}
              />
            )}
          </>
        )}
      </Section>
    </PageShell>
  );
}
