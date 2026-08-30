import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createItem, createVendor, updateItem, updateVendor,
  useItems, useVendors,
  type PriceBookItem, type Vendor,
} from "../api/catalog";
import {
  commitPriceBookSeed, previewPriceBookSeed,
  type PriceBookHarvest,
} from "../api/posimport";
import { useDepartments, type Department } from "../api/dayclose";
import { ApiError } from "../lib/api";
import { fmtMoney2 } from "../lib/formatters";
import { hasPermission } from "../lib/permissions";
import { useUrlFilterState } from "../lib/useUrlFilterState";
import {
  Alert, Breadcrumbs, Button, Card, Checkbox, EmptyState, ErrorState,
  Field, InfoTip, Input, Loading, Modal, PageHeader, PageShell, Pager,
  Pill, RowActions, Section, Select, TabsBar, TabsButton, Table,
  tdStyle, thStyle, useToast,
} from "../components/ui";
import styles from "./PriceBook.module.css";

// /app/price-book — the item catalog + vendor directory (P2-2).
// Two tabs on one page: Items (paginated live search over the
// price book) and Vendors (the supplier directory items link to).
// Everything here is an operator-owned catalog (HANDOFF.md §2
// product principle) — cashiers can look items up (catalog.read),
// managing rows needs catalog.update.

export default function PriceBook() {
  const [tab, setTab] = useState<"items" | "vendors">("items");
  return (
    <PageShell maxWidth="72rem">
      <Breadcrumbs crumbs={[{ label: "Price book" }]} />
      <PageHeader
        title={
          <>
            Price book
            <InfoTip text="Every item the store sells — scan code, price, cost, department, and vendor. Cashiers can look items up; managing the catalog needs admin rights." />
          </>
        }
        subtitle="Items, prices, and the vendors that supply them."
      />
      <TabsBar>
        <TabsButton active={tab === "items"} onClick={() => setTab("items")}>
          Items
        </TabsButton>
        <TabsButton
          active={tab === "vendors"}
          onClick={() => setTab("vendors")}
        >
          Vendors
        </TabsButton>
      </TabsBar>
      {tab === "items" && <ItemsTab />}
      {tab === "vendors" && <VendorsTab />}
    </PageShell>
  );
}

// ── Items tab ────────────────────────────────────────────────

function ItemsTab() {
  const canManage = hasPermission("catalog", "update");
  // 300ms debounce + 2-char minimum via the shared URL-filter hook
  // (CLAUDE.md "Table search UX") — same wiring as Transfers.
  const filters = useUrlFilterState({
    q: "", department_id: "", vendor_id: "", inactive: "",
  });
  const items = useItems({
    q: filters.params.q,
    page: filters.page,
    departmentId: filters.params.department_id,
    vendorId: filters.params.vendor_id,
    includeInactive: filters.params.inactive === "1",
  });
  const departments = useDepartments();
  const vendors = useVendors();
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<PriceBookItem | null>(null);
  const [seeding, setSeeding] = useState(false);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["catalog"] });
  }

  async function toggleActive(item: PriceBookItem) {
    try {
      await updateItem(item.id, { is_active: !item.is_active });
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not update the item.",
        tone: "error",
      });
    }
  }

  const data = items.data;
  return (
    <Section
      title="Items"
      actions={
        canManage ? (
          <div className={styles.toolbarActions}>
            <Button
              size="sm" tone="secondary"
              onClick={() =>
                filters.setParam(
                  "inactive", filters.params.inactive === "1" ? "" : "1",
                )
              }
            >
              {filters.params.inactive === "1"
                ? "Hide inactive" : "Show inactive"}
            </Button>
            <Button
              size="sm" tone="secondary"
              onClick={() => setSeeding(true)}
            >
              Seed from register
            </Button>
            <a
              href="/api/v2/posimport/naxml/pricebook-export"
              download
              style={{ textDecoration: "none" }}
              title="Download the price book as a NAXML ItemMaintenance file for Gilbarco Passport's back-office import (beta — the write-back half of the register loop)."
            >
              <Button size="sm" tone="secondary" type="button">
                Export for register
              </Button>
            </a>
            <Button size="sm" onClick={() => setAdding(true)}>
              + Add item
            </Button>
          </div>
        ) : undefined
      }
    >
      <div className={styles.filtersRow}>
        <div className={styles.searchField}>
          <Field label="Search">
            <Input
              type="search"
              placeholder="Name or scan code…"
              value={filters.draft.q ?? filters.params.q}
              onChange={(e) => filters.debounced("q", e.target.value)}
            />
          </Field>
        </div>
        <Field label="Department">
          <Select
            value={filters.params.department_id}
            onChange={(e) =>
              filters.setParam("department_id", e.target.value)
            }
          >
            <option value="">All</option>
            {(departments.data?.departments ?? []).map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </Select>
        </Field>
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
      </div>
      {items.isLoading && <Loading />}
      {items.isError && (
        <ErrorState
          message="Could not load the price book."
          onRetry={() => { void items.refetch(); }}
        />
      )}
      {data && data.rows.length === 0 && (
        <EmptyState
          title={
            filters.params.q || filters.params.department_id
            || filters.params.vendor_id
              ? "No items match"
              : "No items yet"
          }
          body={
            canManage
              ? 'Add items by hand with "+ Add item" — or click "Seed from register" to build the whole price book from the journal data your register agent uploads.'
              : "The price book is empty."
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
                    {["Scan code", "Item", "Department", "Vendor", "Price",
                      "Cost", "Tax", "Status",
                      ...(canManage ? ["Actions"] : [])].map((h) => (
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((i) => (
                    <tr key={i.id}>
                      <td style={tdStyle}>
                        <span className={styles.posCode}>{i.pos_code}</span>
                        {i.pos_code_format === "plu" && (
                          <>
                            {" "}
                            <Pill tone="neutral">PLU</Pill>
                          </>
                        )}
                      </td>
                      <td style={tdStyle}>{i.name}</td>
                      <td style={tdStyle}>{i.department_name || "—"}</td>
                      <td style={tdStyle}>{i.vendor_name || "—"}</td>
                      <td style={tdStyle}>{fmtMoney2(i.price)}</td>
                      <td style={tdStyle}>
                        {i.cost > 0 ? fmtMoney2(i.cost) : "—"}
                      </td>
                      <td style={tdStyle}>{i.is_taxable ? "Taxable" : "—"}</td>
                      <td style={tdStyle}>
                        <Pill tone={i.is_active ? "accent" : "neutral"}>
                          {i.is_active ? "active" : "inactive"}
                        </Pill>
                      </td>
                      {canManage && (
                        <td style={tdStyle}>
                          <RowActions
                            title={i.name}
                            actions={[
                              {
                                label: "Edit",
                                tone: "primary",
                                onClick: () => setEditing(i),
                              },
                              {
                                label: i.is_active
                                  ? "Deactivate" : "Reactivate",
                                tone: i.is_active ? "warning" : "primary",
                                onClick: () => toggleActive(i),
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
      <ItemModal
        open={adding || editing != null}
        existing={editing}
        departments={departments.data?.departments ?? []}
        vendors={vendors.data?.vendors ?? []}
        onClose={() => { setAdding(false); setEditing(null); }}
        onDone={() => { setAdding(false); setEditing(null); refresh(); }}
      />
      <SeedModal
        open={seeding}
        onClose={() => setSeeding(false)}
        onDone={() => { setSeeding(false); refresh(); }}
      />
    </Section>
  );
}

// ── Seed-from-register modal (P2-3 warm start) ───────────────

function SeedModal({
  open, onClose, onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        <>
          Seed from register data
          <InfoTip text="Reads every journal file your register agent has uploaded and builds price-book entries from the items it sold — scan code, name, latest shelf price, and the department your merchandise-code mapping points at. Items you already added are never touched." />
        </>
      }
    >
      {open && <SeedPreview onClose={onClose} onDone={onDone} />}
    </Modal>
  );
}

function SeedPreview({
  onClose, onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  // Fresh fetch per open: the preview re-parses staged journals
  // server-side, so never serve it from cache.
  const previewQuery = useQuery<PriceBookHarvest>({
    queryKey: ["posimport", "pricebook-preview"],
    queryFn: previewPriceBookSeed,
    gcTime: 0,
    staleTime: 0,
  });
  const preview = previewQuery.data ?? null;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function onCommit() {
    setBusy(true);
    setError(null);
    try {
      const result = await commitPriceBookSeed();
      toast({
        message: `${result.created} item(s) added from register data`
          + (result.skipped_existing
            ? ` (${result.skipped_existing} already in your price book)`
            : "."),
        tone: "success",
      });
      onDone();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not seed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.modalForm}>
      {error && <Alert tone="error">{error}</Alert>}
      {previewQuery.isLoading && <Loading />}
      {previewQuery.isError && (
        <ErrorState
          message="Could not read the register data."
          onRetry={() => { void previewQuery.refetch(); }}
        />
      )}
      {preview != null && preview.items.length === 0 && (
        <EmptyState
          title="No register data yet"
          body="Once your site agent has uploaded journal files (see Day close → Import from register), items it sold show up here."
        />
      )}
      {preview != null && preview.items.length > 0 && (
        <>
          <p>
            Found <strong>{preview.items.length}</strong> distinct
            item(s) in the uploaded journals —{" "}
            <strong>{preview.new_count}</strong> new,{" "}
            {preview.existing_count} already in your price book.
            New items land with their latest shelf price and stay
            fully editable.
          </p>
          <div style={{ overflowX: "auto", maxHeight: "18rem" }}>
            <Table>
              <thead>
                <tr>
                  {["Scan code", "Item", "Department", "Price", ""].map(
                    (h) => <th key={h} style={thStyle}>{h}</th>,
                  )}
                </tr>
              </thead>
              <tbody>
                {preview.items.slice(0, 50).map((i) => (
                  <tr key={i.pos_code}>
                    <td style={tdStyle}>
                      <span className={styles.posCode}>{i.pos_code}</span>
                    </td>
                    <td style={tdStyle}>{i.description || "—"}</td>
                    <td style={tdStyle}>{i.department_name || "—"}</td>
                    <td style={tdStyle}>{fmtMoney2(i.price)}</td>
                    <td style={tdStyle}>
                      {i.already_in_price_book && (
                        <Pill tone="neutral">already added</Pill>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
          {preview.items.length > 50 && (
            <p>…and {preview.items.length - 50} more.</p>
          )}
        </>
      )}
      <div className={styles.modalActions}>
        <Button tone="secondary" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button
          type="button" busy={busy}
          disabled={busy || preview == null || preview.new_count === 0}
          onClick={() => { void onCommit(); }}
        >
          {preview != null && preview.new_count > 0
            ? `Add ${preview.new_count} item(s)`
            : "Nothing to add"}
        </Button>
      </div>
    </div>
  );
}

// ── Item modal (add / edit one price-book item) ──────────────

function ItemModal({
  open, existing, departments, vendors, onClose, onDone,
}: {
  open: boolean;
  existing: PriceBookItem | null;
  departments: Department[];
  vendors: Vendor[];
  onClose: () => void;
  onDone: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={existing ? `Edit ${existing.name}` : "Add an item"}
    >
      {open && (
        // Keyed remount resets the form per open/target — prefill
        // via initializers, no state-sync effect needed.
        <ItemForm
          key={existing?.id ?? "new"}
          existing={existing}
          departments={departments}
          vendors={vendors}
          onClose={onClose}
          onDone={onDone}
        />
      )}
    </Modal>
  );
}

function ItemForm({
  existing, departments, vendors, onClose, onDone,
}: {
  existing: PriceBookItem | null;
  departments: Department[];
  vendors: Vendor[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [posCode, setPosCode] = useState(existing?.pos_code ?? "");
  const [posFormat, setPosFormat] = useState(
    existing?.pos_code_format ?? "upc",
  );
  const [name, setName] = useState(existing?.name ?? "");
  const [departmentId, setDepartmentId] = useState(
    existing?.department_id != null ? String(existing.department_id) : "",
  );
  const [vendorId, setVendorId] = useState(
    existing?.vendor_id != null ? String(existing.vendor_id) : "",
  );
  const [price, setPrice] = useState(
    existing ? String(existing.price) : "",
  );
  const [cost, setCost] = useState(
    existing && existing.cost > 0 ? String(existing.cost) : "",
  );
  const [taxable, setTaxable] = useState(existing?.is_taxable ?? true);
  // Item-editor parity (P2-5): vendor item #, size label, case
  // pack, EBT, margin helper.
  const [itemNumber, setItemNumber] = useState(existing?.item_number ?? "");
  const [size, setSize] = useState(existing?.size ?? "");
  const [caseSize, setCaseSize] = useState(
    existing?.case_size != null ? String(existing.case_size) : "",
  );
  const [caseCost, setCaseCost] = useState(
    existing?.case_cost != null ? String(existing.case_cost) : "",
  );
  const [ebt, setEbt] = useState(existing?.is_ebt ?? false);
  const [marginGoal, setMarginGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cronysoft-style Department → Sub Department cascade. The flat
  // department list carries parent_id; departmentId always holds
  // the LEAF that gets stored on the item (a sub-department when
  // one is picked, else the parent). Both selects derive from it.
  const parents = departments.filter((d) => d.parent_id == null);
  const currentDept = departments.find(
    (d) => String(d.id) === departmentId,
  );
  const parentSel =
    currentDept == null
      ? ""
      : String(currentDept.parent_id ?? currentDept.id);
  const subSel = currentDept?.parent_id != null ? departmentId : "";
  const subs = departments.filter(
    (d) => parentSel !== "" && d.parent_id === Number(parentSel),
  );

  // Derived numbers for the pricing helpers.
  const priceNum = Number.parseFloat(price) || 0;
  const costNum = Number.parseFloat(cost) || 0;
  const caseSizeNum = Number.parseInt(caseSize, 10) || 0;
  const caseCostNum = Number.parseFloat(caseCost) || 0;
  const unitFromCase =
    caseSizeNum > 0 && caseCostNum > 0 ? caseCostNum / caseSizeNum : null;
  const margin =
    priceNum > 0 ? ((priceNum - costNum) / priceNum) * 100 : null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (existing) {
        await updateItem(existing.id, {
          pos_code: posCode.trim(),
          pos_code_format: posFormat,
          name: name.trim(),
          // 0 clears an optional link (None = leave unchanged
          // server-side, so "" must map to the explicit clear).
          department_id: departmentId === "" ? 0 : Number(departmentId),
          vendor_id: vendorId === "" ? 0 : Number(vendorId),
          price: Number.parseFloat(price) || 0,
          cost: Number.parseFloat(cost) || 0,
          is_taxable: taxable,
          item_number: itemNumber.trim(),
          size: size.trim(),
          // 0 clears the nullable case fields server-side.
          case_size: caseSizeNum > 0 ? caseSizeNum : 0,
          case_cost: caseCostNum > 0 ? caseCostNum : 0,
          is_ebt: ebt,
        });
      } else {
        await createItem({
          pos_code: posCode.trim(),
          pos_code_format: posFormat,
          name: name.trim(),
          department_id: departmentId === "" ? null : Number(departmentId),
          vendor_id: vendorId === "" ? null : Number(vendorId),
          price: Number.parseFloat(price) || 0,
          cost: Number.parseFloat(cost) || 0,
          is_taxable: taxable,
          item_number: itemNumber.trim(),
          size: size.trim(),
          case_size: caseSizeNum > 0 ? caseSizeNum : null,
          case_cost: caseCostNum > 0 ? caseCostNum : null,
          is_ebt: ebt,
        });
      }
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className={styles.modalForm}>
      {error && <Alert tone="error">{error}</Alert>}
      <div className={styles.fieldGrid}>
        <Field
          label={
            <>
              Scan code
              <InfoTip text="The UPC as printed under the barcode, or the short PLU number keyed at the register. Leading zeros are kept." />
            </>
          }
        >
          <Input
            type="text" value={posCode} required maxLength={30}
            onChange={(e) => setPosCode(e.target.value)}
          />
        </Field>
        <Field label="Code type">
          <Select
            value={posFormat}
            onChange={(e) => setPosFormat(e.target.value)}
          >
            <option value="upc">UPC (scanned)</option>
            <option value="plu">PLU (keyed)</option>
          </Select>
        </Field>
      </div>
      <Field label="Item name">
        <Input
          type="text" value={name} required maxLength={160}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <div className={styles.fieldGrid}>
        <Field label="Department (optional)">
          <Select
            value={parentSel}
            onChange={(e) => setDepartmentId(e.target.value)}
          >
            <option value="">None</option>
            {parents.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Sub-department">
          <Select
            value={subSel}
            disabled={subs.length === 0}
            onChange={(e) =>
              setDepartmentId(e.target.value || parentSel)
            }
          >
            <option value="">
              {subs.length === 0 ? "—" : "None"}
            </option>
            {subs.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Vendor (optional)">
          <Select
            value={vendorId}
            onChange={(e) => setVendorId(e.target.value)}
          >
            <option value="">None</option>
            {vendors.map((v) => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Sales tax">
          <Checkbox checked={taxable} onChange={setTaxable}>
            Taxable
          </Checkbox>
        </Field>
        <Field label="Item # (optional)">
          <Input
            type="text" value={itemNumber} maxLength={40}
            placeholder="Vendor order number"
            onChange={(e) => setItemNumber(e.target.value)}
          />
        </Field>
        <Field label="Item size (optional)">
          <Input
            type="text" value={size} maxLength={40}
            placeholder="12oz / POUND / 6-pack"
            onChange={(e) => setSize(e.target.value)}
          />
        </Field>
        <Field label="Case size">
          <Input
            type="number" min={0} step="1" value={caseSize}
            placeholder="Units per case"
            onChange={(e) => setCaseSize(e.target.value)}
          />
        </Field>
        <Field
          label="Case cost"
          hint={
            unitFromCase != null
              ? `Unit cost from case: $${unitFromCase.toFixed(4)}`
              : undefined
          }
        >
          <Input
            type="number" min={0} step="0.01" value={caseCost}
            onChange={(e) => setCaseCost(e.target.value)}
          />
        </Field>
        <Field
          label="Unit cost (optional)"
          hint={
            unitFromCase != null && cost === ""
              ? "Empty — saves as $0; use the case-derived value?"
              : undefined
          }
        >
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <Input
              type="number" min={0} step="0.01" value={cost}
              onChange={(e) => setCost(e.target.value)}
            />
            {unitFromCase != null && (
              <Button
                type="button" tone="secondary" size="sm"
                onClick={() => setCost(unitFromCase.toFixed(2))}
              >
                Use case
              </Button>
            )}
          </div>
        </Field>
        <Field
          label="Retail price"
          hint={
            margin != null
              ? `Margin: ${margin.toFixed(2)}%`
              : undefined
          }
        >
          <Input
            type="number" min={0} step="0.01" value={price} required
            onChange={(e) => setPrice(e.target.value)}
          />
        </Field>
        <Field
          label="Margin goal %"
          hint="Sets the retail price from the unit cost."
        >
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <Input
              type="number" min={0} max={99} step="0.01"
              value={marginGoal}
              placeholder="e.g. 40"
              onChange={(e) => setMarginGoal(e.target.value)}
            />
            <Button
              type="button" tone="secondary" size="sm"
              disabled={
                costNum <= 0
                || !(Number.parseFloat(marginGoal) > 0)
                || Number.parseFloat(marginGoal) >= 100
              }
              onClick={() => {
                const g = Number.parseFloat(marginGoal);
                setPrice((costNum / (1 - g / 100)).toFixed(2));
              }}
            >
              Apply
            </Button>
          </div>
        </Field>
      </div>
      <Checkbox
        checked={ebt} onChange={setEbt}
        style={{ marginTop: "0.75rem" }}
      >
        EBT / SNAP eligible
      </Checkbox>
      <div className={styles.modalActions}>
        <Button tone="secondary" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" busy={busy} disabled={busy}>
          {existing ? "Save changes" : "Add item"}
        </Button>
      </div>
    </form>
  );
}

// ── Vendors tab ──────────────────────────────────────────────

function VendorsTab() {
  const canManage = hasPermission("catalog", "update");
  const [showInactive, setShowInactive] = useState(false);
  const vendors = useVendors(showInactive);
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Vendor | null>(null);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["catalog"] });
  }

  async function toggleActive(v: Vendor) {
    try {
      await updateVendor(v.id, { is_active: !v.is_active });
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not update the vendor.",
        tone: "error",
      });
    }
  }

  return (
    <Section
      title="Vendors"
      actions={
        canManage ? (
          <div className={styles.toolbarActions}>
            <Button
              size="sm" tone="secondary"
              onClick={() => setShowInactive((v) => !v)}
            >
              {showInactive ? "Hide inactive" : "Show inactive"}
            </Button>
            <Button size="sm" onClick={() => setAdding(true)}>
              + Add vendor
            </Button>
          </div>
        ) : undefined
      }
    >
      {vendors.isLoading && <Loading />}
      {vendors.isError && (
        <ErrorState
          message="Could not load vendors."
          onRetry={() => { void vendors.refetch(); }}
        />
      )}
      {vendors.data && vendors.data.vendors.length === 0 && (
        <EmptyState
          title="No vendors yet"
          body={
            canManage
              ? "Add the suppliers you buy from — items link to them, and purchase invoices will too."
              : "No vendors on file."
          }
          cta={
            canManage ? (
              <Button size="sm" onClick={() => setAdding(true)}>
                + Add vendor
              </Button>
            ) : undefined
          }
        />
      )}
      {vendors.data && vendors.data.vendors.length > 0 && (
        <Card>
          <div style={{ overflowX: "auto" }}>
            <Table>
              <thead>
                <tr>
                  {["Vendor", "Contact", "Phone", "Account #", "Items",
                    "Status", ...(canManage ? ["Actions"] : [])].map((h) => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {vendors.data.vendors.map((v) => (
                  <tr key={v.id}>
                    <td style={tdStyle}>{v.name}</td>
                    <td style={tdStyle}>{v.contact_name || "—"}</td>
                    <td style={tdStyle}>{v.phone || "—"}</td>
                    <td style={tdStyle}>
                      {v.account_number
                        ? (
                          <span className={styles.posCode}>
                            {v.account_number}
                          </span>
                        )
                        : "—"}
                    </td>
                    <td style={tdStyle}>{v.item_count}</td>
                    <td style={tdStyle}>
                      <Pill tone={v.is_active ? "accent" : "neutral"}>
                        {v.is_active ? "active" : "inactive"}
                      </Pill>
                    </td>
                    {canManage && (
                      <td style={tdStyle}>
                        <RowActions
                          title={v.name}
                          actions={[
                            {
                              label: "Edit",
                              tone: "primary",
                              onClick: () => setEditing(v),
                            },
                            {
                              label: v.is_active
                                ? "Deactivate" : "Reactivate",
                              tone: v.is_active ? "warning" : "primary",
                              onClick: () => toggleActive(v),
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
      )}
      <VendorModal
        open={adding || editing != null}
        existing={editing}
        onClose={() => { setAdding(false); setEditing(null); }}
        onDone={() => { setAdding(false); setEditing(null); refresh(); }}
      />
    </Section>
  );
}

function VendorModal({
  open, existing, onClose, onDone,
}: {
  open: boolean;
  existing: Vendor | null;
  onClose: () => void;
  onDone: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={existing ? `Edit ${existing.name}` : "Add a vendor"}
    >
      {open && (
        // Keyed remount resets the form per open/target — prefill
        // via initializers, no state-sync effect needed.
        <VendorForm
          key={existing?.id ?? "new"}
          existing={existing}
          onClose={onClose}
          onDone={onDone}
        />
      )}
    </Modal>
  );
}

function VendorForm({
  existing, onClose, onDone,
}: {
  existing: Vendor | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(existing?.name ?? "");
  const [contact, setContact] = useState(existing?.contact_name ?? "");
  const [phone, setPhone] = useState(existing?.phone ?? "");
  const [email, setEmail] = useState(existing?.email ?? "");
  const [account, setAccount] = useState(existing?.account_number ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      name: name.trim(),
      contact_name: contact.trim(),
      phone: phone.trim(),
      email: email.trim(),
      account_number: account.trim(),
      notes: notes.trim(),
    };
    try {
      if (existing) {
        await updateVendor(existing.id, body);
      } else {
        await createVendor(body);
      }
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className={styles.modalForm}>
      {error && <Alert tone="error">{error}</Alert>}
      <Field label="Vendor name">
        <Input
          type="text" value={name} required maxLength={120}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <div className={styles.fieldGrid}>
        <Field label="Contact (optional)">
          <Input
            type="text" value={contact} maxLength={120}
            onChange={(e) => setContact(e.target.value)}
          />
        </Field>
        <Field label="Phone (optional)">
          <Input
            type="tel" value={phone} maxLength={30}
            onChange={(e) => setPhone(e.target.value)}
          />
        </Field>
        <Field label="Email (optional)">
          <Input
            type="email" value={email} maxLength={200}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field
          label={
            <>
              Account # (optional)
              <InfoTip text="Your store's account number with this vendor — as printed on their invoices." />
            </>
          }
        >
          <Input
            type="text" value={account} maxLength={60}
            onChange={(e) => setAccount(e.target.value)}
          />
        </Field>
      </div>
      <Field label="Notes (optional)">
        <Input
          type="text" value={notes} maxLength={500}
          onChange={(e) => setNotes(e.target.value)}
        />
      </Field>
      <div className={styles.modalActions}>
        <Button tone="secondary" type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" busy={busy} disabled={busy}>
          {existing ? "Save changes" : "Add vendor"}
        </Button>
      </div>
    </form>
  );
}
