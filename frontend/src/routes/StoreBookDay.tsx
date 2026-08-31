import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  restoreStoreBookField, setStoreBookLock, updateStoreBookDay,
  useStoreBookDay,
  type StoreBookField,
} from "../api/storebook";
import {
  Alert, Breadcrumbs, Button, Card, ConfirmDialog, ErrorState, Field,
  IconButton, Input, Loading, MoneyInput, PageHeader, PageShell,
  Textarea, useToast,
} from "../components/ui";
import RegisterCloses from "../components/RegisterCloses";
import { ApiError } from "../lib/api";
import { fmtMoney2 } from "../lib/formatters";
import { formatDate } from "../lib/datetime";
import styles from "./StoreBookDay.module.css";

// /app/store-book/day?date=YYYY-MM-DD — one store day.
//
// Three columns that balance: Sales, Tenders, Deposit & balance.
// over/short is tenders − sales and it is the point of the page,
// so it recomputes as you type rather than on save.
//
// The layout comes from the API (`layout`), not from a copy here —
// a new field on the sheet appears without a frontend change.

function todayIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// MoneyInput works in DOLLARS; the API and the totals work in
// cents. These two are the only place the boundary is crossed.
function centsToDollars(cents: number): number {
  return cents / 100;
}
function dollarsToCents(dollars: number): number {
  return Math.round((dollars || 0) * 100);
}

export default function StoreBookDay() {
  const [sp, setSP] = useSearchParams();
  const day = sp.get("date") || todayIso();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();

  const { data, isLoading, isError, refetch } = useStoreBookDay(day);

  // Local edit buffer. MoneyInput is a controlled number field, so
  // money is held in dollars; counts stay strings. Flushed to the
  // server on blur.
  const [money, setMoney] = useState<Record<string, number>>({});
  const [counts, setCounts] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [confirmLock, setConfirmLock] = useState(false);

  useEffect(() => {
    if (!data) return;
    const m: Record<string, number> = {};
    for (const [k, v] of Object.entries(data.values)) {
      m[k] = centsToDollars(v);
    }
    const c: Record<string, string> = {};
    for (const [k, v] of Object.entries(data.counts)) {
      c[k] = v ? String(v) : "";
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate the local edit buffer from the fetched day
    setMoney(m);
    setCounts(c);
    setNotes(data.notes || "");
  }, [data]);

  // Totals recomputed from the buffer so the header tracks typing
  // rather than the last save. Column membership comes from the
  // server-supplied layout, so this can't disagree with the API.
  const totals = useMemo(() => {
    const out = { sales: 0, tenders: 0, deposit: 0 };
    if (!data) return { ...out, overShort: 0 };
    for (const column of data.layout) {
      for (const section of column.sections) {
        for (const f of section.fields) {
          const key = column.column as keyof typeof out;
          out[key] += dollarsToCents(money[f.key] ?? 0);
        }
      }
    }
    return { ...out, overShort: out.tenders - out.sales };
  }, [data, money]);

  const locked = data?.is_locked ?? false;

  async function flush(body: Parameters<typeof updateStoreBookDay>[1]) {
    if (locked) return;
    setBusy(true);
    setServerError(null);
    try {
      const next = await updateStoreBookDay(day, body);
      qc.setQueryData(
        ["storebook", "day", next.store_id, day], next,
      );
      void qc.invalidateQueries({ queryKey: ["storebook", "month"] });
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "Could not save.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onToggleLock() {
    setBusy(true);
    try {
      const next = await setStoreBookLock(day, !locked);
      qc.setQueryData(["storebook", "day", next.store_id, day], next);
      void qc.invalidateQueries({ queryKey: ["storebook", "month"] });
      toast({
        message: next.is_locked ? "Day locked." : "Day unlocked.",
        tone: "success",
      });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not change the lock.",
        tone: "error",
      });
    } finally {
      setBusy(false);
      setConfirmLock(false);
    }
  }

  async function onRestore(fieldKey: string) {
    setBusy(true);
    try {
      const next = await restoreStoreBookField(day, fieldKey);
      qc.setQueryData(["storebook", "day", next.store_id, day], next);
      toast({ message: "Register value restored.", tone: "success" });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not restore.",
        tone: "error",
      });
    } finally {
      setBusy(false);
    }
  }

  function shiftDay(delta: number) {
    const d = new Date(`${day}T00:00:00`);
    d.setDate(d.getDate() + delta);
    const p = (n: number) => String(n).padStart(2, "0");
    const next =
      `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    const params = new URLSearchParams(sp);
    params.set("date", next);
    setSP(params, { replace: true });
  }

  if (isLoading) {
    return (
      <PageShell>
        <PageHeader title="Daily book" />
        <Loading />
      </PageShell>
    );
  }
  if (isError || !data) {
    return (
      <PageShell>
        <PageHeader title="Daily book" />
        <ErrorState
          message="Couldn't load this day."
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="76rem">
      <Breadcrumbs crumbs={[
        { label: "Daily book", to: "/store-book" },
        { label: formatDate(day) },
      ]} />

      <PageHeader
        title="Daily book"
        subtitle={formatDate(day)}
        actions={
          <div className={styles.dayNav}>
            <Button
              tone="secondary" size="sm"
              onClick={() => shiftDay(-1)} aria-label="Previous day"
            >
              ←
            </Button>
            <Input
              type="date" value={day}
              onChange={(e) => {
                const params = new URLSearchParams(sp);
                params.set("date", e.target.value);
                setSP(params, { replace: true });
              }}
            />
            <Button
              tone="secondary" size="sm"
              onClick={() => shiftDay(1)} aria-label="Next day"
            >
              →
            </Button>
            <Button
              tone={locked ? "primary" : "secondary"} size="sm"
              busy={busy}
              onClick={() => {
                if (locked) void onToggleLock();
                else setConfirmLock(true);
              }}
            >
              {locked ? "Unlock" : "Lock day"}
            </Button>
          </div>
        }
      />

      {locked && (
        <Alert tone="info">
          This day is locked. Unlock it to make changes — imported
          register data still lands while it's locked.
        </Alert>
      )}
      {serverError && <Alert tone="error">{serverError}</Alert>}

      {/* The three running totals. over/short is the one that
          matters; it's given its own tone so a shortage reads as a
          shortage at a glance. */}
      <div className={styles.totalsRow}>
        <div className={`${styles.totalCard} ${styles.sales}`}>
          <span className={styles.totalLabel}>Sales</span>
          <span className={styles.totalValue}>
            {fmtMoney2(totals.sales / 100)}
          </span>
        </div>
        <div className={`${styles.totalCard} ${styles.tenders}`}>
          <span className={styles.totalLabel}>Tenders</span>
          <span className={styles.totalValue}>
            {fmtMoney2(totals.tenders / 100)}
          </span>
        </div>
        <div className={`${styles.totalCard} ${styles.deposit}`}>
          <span className={styles.totalLabel}>Deposit &amp; balance</span>
          <span className={styles.totalValue}>
            {fmtMoney2(totals.deposit / 100)}
          </span>
        </div>
        <div
          className={`${styles.totalCard} ${
            totals.overShort === 0
              ? styles.balanced
              : totals.overShort > 0 ? styles.over : styles.short
          }`}
        >
          <span className={styles.totalLabel}>
            {totals.overShort === 0
              ? "Balanced"
              : totals.overShort > 0 ? "Over" : "Short"}
          </span>
          <span className={styles.totalValue}>
            {fmtMoney2(Math.abs(totals.overShort) / 100)}
          </span>
        </div>
      </div>

      <div className={styles.columns}>
        {data.layout.map((column) => (
          <div key={column.column} className={styles.column}>
            <div
              className={`${styles.columnHead} ${styles[column.column]}`}
            >
              {column.label}
            </div>
            {column.sections.map((section) => (
              <Card key={section.key} className={styles.section}>
                <div className={styles.sectionTitle}>{section.label}</div>
                {section.fields.map((f) => (
                  <MoneyRow
                    key={f.key}
                    field={f}
                    day={day}
                    locked={locked}
                    value={money[f.key] ?? 0}
                    countValue={
                      f.count_field ? counts[f.count_field] ?? "" : ""
                    }
                    gallonsValue={
                      f.gallons_field ? counts[f.gallons_field] ?? "" : ""
                    }
                    original={data.originals[f.key]}
                    onMoney={(v) =>
                      setMoney((m) => ({ ...m, [f.key]: v }))}
                    onCount={(v) => {
                      if (f.count_field) {
                        setCounts((c) => ({ ...c, [f.count_field!]: v }));
                      }
                    }}
                    onGallons={(v) => {
                      if (f.gallons_field) {
                        setCounts((c) => ({ ...c, [f.gallons_field!]: v }));
                      }
                    }}
                    onCommit={() => {
                      const body: Parameters<typeof updateStoreBookDay>[1] = {
                        values: {
                          [f.key]: dollarsToCents(money[f.key] ?? 0),
                        },
                      };
                      const c: Record<string, number> = {};
                      if (f.count_field) {
                        c[f.count_field] =
                          Number(counts[f.count_field] ?? 0) || 0;
                      }
                      if (f.gallons_field) {
                        c[f.gallons_field] =
                          Number(counts[f.gallons_field] ?? 0) || 0;
                      }
                      if (Object.keys(c).length) body.counts = c;
                      void flush(body);
                    }}
                    onRestore={() => { void onRestore(f.key); }}
                  />
                ))}
              </Card>
            ))}
          </div>
        ))}
      </div>

      {/* Per-register Z-report detail for the same day. The sheet
          above is what the store banked; this is which drawer it
          came out of — one screen, one day. */}
      <RegisterCloses day={day} canEdit={!locked} />

      <Card>
        <Field label="Notes">
          <Textarea
            rows={3}
            value={notes}
            disabled={locked}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={() => { void flush({ notes }); }}
          />
        </Field>
      </Card>

      <ConfirmDialog
        open={confirmLock}
        title="Lock this day"
        message="Locking stops further edits until an admin unlocks it. Imported register data still lands while locked."
        confirmLabel="Lock day"
        busy={busy}
        onConfirm={() => { void onToggleLock(); }}
        onCancel={() => setConfirmLock(false)}
      />

      <div className={styles.footerRow}>
        <Button tone="secondary" onClick={() => navigate("/store-book")}>
          Back to the month
        </Button>
      </div>
    </PageShell>
  );
}


/** One money input, with its optional count/gallons companion and
 *  the "Orig. Val" caption when the register supplied a value. */
function MoneyRow({
  field, locked, value, countValue, gallonsValue, original,
  onMoney, onCount, onGallons, onCommit, onRestore,
}: {
  field: StoreBookField;
  day: string;
  locked: boolean;
  value: number;
  countValue: string;
  gallonsValue: string;
  original?: number;
  onMoney: (v: number) => void;
  onCount: (v: string) => void;
  onGallons: (v: string) => void;
  onCommit: () => void;
  onRestore: () => void;
}) {
  const cents = dollarsToCents(value);
  // Green when the operator's value still matches what the register
  // said; red once they've overridden it. Matches the convention
  // operators already know from other back-office tools.
  const overridden = original != null && original !== cents;

  return (
    <div className={styles.row}>
      <span className={styles.rowLabel}>{field.label}</span>
      <div className={styles.rowInputs} onBlur={onCommit}>
        {field.count_field && (
          <Input
            type="number" inputMode="numeric"
            className={styles.countInput}
            aria-label={`${field.label} count`}
            placeholder="#"
            value={countValue}
            disabled={locked}
            onChange={(e) => onCount(e.target.value)}
          />
        )}
        {field.gallons_field && (
          <Input
            type="number" step="0.001" inputMode="decimal"
            className={styles.countInput}
            aria-label="Gallons"
            placeholder="gal"
            value={gallonsValue}
            disabled={locked}
            onChange={(e) => onGallons(e.target.value)}
          />
        )}
        <MoneyInput
          aria-label={field.label}
          value={value}
          onChange={onMoney}
          disabled={locked}
          fullWidth
        />
        {overridden && !locked && (
          <IconButton
            aria-label="Restore the register's value"
            title="Restore the register's value"
            onClick={onRestore}
          >
            ↻
          </IconButton>
        )}
      </div>
      {original != null && (
        <div
          className={`${styles.orig} ${
            overridden ? styles.origChanged : styles.origMatch
          }`}
        >
          Orig. Val: {fmtMoney2(original / 100)}
        </div>
      )}
    </div>
  );
}
