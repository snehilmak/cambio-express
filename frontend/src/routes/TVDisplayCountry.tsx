import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useTVDisplayCountryDetail,
  type TVDisplayBankRow,
} from "../api/tvDisplay";
import {
  Breadcrumbs,
  Button, ButtonLink, Card, ErrorState, Field, Input, Loading, PageHeader,
  PageShell, Table, tdStyle, thStyle,
} from "../components/ui";
import styles from "./TVDisplayCountry.module.css";

// /app/tv-display/countries/:id — country editor for the rate
// board. The mutation surface (banks add/remove, rate matrix
// upsert) still POSTs to legacy Flask at
// /tv-display/countries/<id> (form-encoded). The SPA renders
// the editor and submits the form natively — Flask returns
// 302 → /tv-display → 301 → /app/tv-display, so the operator
// lands back on the picker after save.
export default function TVDisplayCountry() {
  const { countryId } = useParams<{ countryId: string }>();
  const cid = Number(countryId);
  const { data, isLoading, isError, error, refetch } =
    useTVDisplayCountryDetail(cid);

  const [companiesText, setCompaniesText] = useState("");
  const [bankNames, setBankNames] = useState<Record<number, string>>({});
  const [bankSorts, setBankSorts] = useState<Record<number, number>>({});
  const [bankDeletes, setBankDeletes] = useState<Set<number>>(new Set());
  const [newBankNames, setNewBankNames] = useState<string[]>([""]);
  const [rateGrid, setRateGrid] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable country/bank/rate grid from server-fetched config; resets pending deletes/new-bank rows on each refresh
    setCompaniesText(data.mt_companies.join(","));
    setBankNames(Object.fromEntries(data.banks.map((b) => [b.id, b.bank_name])));
    setBankSorts(Object.fromEntries(data.banks.map((b) => [b.id, b.sort_order])));
    setBankDeletes(new Set());
    setNewBankNames([""]);
    const grid: Record<string, string> = {};
    for (const b of data.banks) {
      data.mt_companies.forEach((co, idx) => {
        const v = b.rates[co];
        if (typeof v === "number") {
          grid[`rate-${b.id}-${idx}`] = String(v);
        }
      });
    }
    setRateGrid(grid);
  }, [data]);

  const companies = useMemo(
    () => companiesText.split(",").map((s) => s.trim()).filter(Boolean),
    [companiesText],
  );

  if (isLoading) {
    return (
      <PageShell maxWidth="75rem">
        <Loading label="Loading country…" />
      </PageShell>
    );
  }
  if (isError || !data) {
    return (
      <PageShell maxWidth="75rem">
        <ErrorState
          message={`Couldn't load country — ${error instanceof Error ? error.message : "unknown error"}`}
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  function setRate(bankId: number, idx: number, value: string) {
    setRateGrid((g) => ({ ...g, [`rate-${bankId}-${idx}`]: value }));
  }

  function setNewBankAt(idx: number, value: string) {
    setNewBankNames((ns) => {
      const out = [...ns];
      out[idx] = value;
      // Keep one empty trailing input so adding a row is implicit.
      const trailing = out[out.length - 1];
      if (trailing.trim().length > 0) out.push("");
      return out;
    });
  }

  return (
    <PageShell maxWidth="75rem">
      <div>
        <Link to="/tv-display" className={styles.backLink}>← Back to TV Display</Link>

        <Breadcrumbs crumbs={[{ label: "TV Display", to: "/tv-display/content" }, { label: "Country" }]} />

        <PageHeader
          title={data.country_name || "Country"}
          subtitle={
            `${data.country_code} · ${data.banks.length} bank` +
            `${data.banks.length === 1 ? "" : "s"} · ` +
            `${data.mt_companies.length} company column` +
            `${data.mt_companies.length === 1 ? "" : "s"}`
          }
        />
      </div>

      <form
        method="POST"
        action={`/tv-display/countries/${cid}`}
        className={styles.form}
      >
        <Card>
          <h2 className={styles.cardH2}>Country header</h2>
          <Field label="Country name">
            <Input
              name="country_name"
              defaultValue={data.country_name}
              maxLength={80}
            />
          </Field>
          <Field label="ISO country code">
            <Input
              name="country_code"
              defaultValue={data.country_code}
              maxLength={4}
            />
          </Field>
          <Field
            label="MT companies (comma-separated slugs)"
            hint="These become the column headers in the public board's rate grid. Order is preserved."
          >
            <Input
              name="mt_companies"
              value={companiesText}
              onChange={(e) => setCompaniesText(e.target.value)}
              maxLength={500}
            />
          </Field>
        </Card>

        <Card>
          <h2 className={styles.cardH2}>Banks &amp; rate matrix</h2>
          <Table>
            <thead>
              <tr>
                <th style={thStyle}>Bank</th>
                <th style={thStyle}>Order</th>
                {companies.map((co) => (
                  <th key={co} style={thStyle}>{co}</th>
                ))}
                <th style={thStyle}>Delete</th>
              </tr>
            </thead>
            <tbody>
              {data.banks.map((b) => (
                <BankRow
                  key={b.id}
                  bank={b}
                  companies={companies}
                  bankName={bankNames[b.id] ?? b.bank_name}
                  setBankName={(v) =>
                    setBankNames((s) => ({ ...s, [b.id]: v }))
                  }
                  bankSort={bankSorts[b.id] ?? b.sort_order}
                  setBankSort={(v) =>
                    setBankSorts((s) => ({ ...s, [b.id]: v }))
                  }
                  toDelete={bankDeletes.has(b.id)}
                  toggleDelete={() =>
                    setBankDeletes((s) => {
                      const n = new Set(s);
                      if (n.has(b.id)) n.delete(b.id);
                      else n.add(b.id);
                      return n;
                    })
                  }
                  rateGrid={rateGrid}
                  setRate={setRate}
                />
              ))}
            </tbody>
          </Table>
        </Card>

        <Card>
          <h2 className={styles.cardH2}>Add new banks</h2>
          {newBankNames.map((name, idx) => (
            <Input
              key={idx}
              name="new_bank_name"
              value={name}
              onChange={(e) => setNewBankAt(idx, e.target.value)}
              placeholder="Bank name (leave blank to skip)"
              maxLength={120}
              className={styles.newBankInput}
            />
          ))}
        </Card>

        <div className={styles.actions}>
          <Button type="submit">Save changes</Button>
          <ButtonLink href="/tv-display" tone="secondary">Cancel</ButtonLink>
        </div>
      </form>
    </PageShell>
  );
}

function BankRow({
  bank, companies, bankName, setBankName, bankSort, setBankSort,
  toDelete, toggleDelete, rateGrid, setRate,
}: {
  bank: TVDisplayBankRow;
  companies: string[];
  bankName: string;
  setBankName: (v: string) => void;
  bankSort: number;
  setBankSort: (v: number) => void;
  toDelete: boolean;
  toggleDelete: () => void;
  rateGrid: Record<string, string>;
  setRate: (bankId: number, idx: number, v: string) => void;
}) {
  return (
    <tr className={toDelete ? styles.rowToDelete : undefined}>
      <td style={tdStyle}>
        <Input
          name={`bank-${bank.id}-name`}
          value={bankName}
          onChange={(e) => setBankName(e.target.value)}
          maxLength={120}
        />
      </td>
      <td style={tdStyle}>
        <Input
          name={`bank-${bank.id}-sort`}
          type="number"
          value={bankSort}
          onChange={(e) => setBankSort(Number(e.target.value) || 0)}
          style={{ width: "5rem" }}
        />
      </td>
      {companies.map((_, idx) => (
        <td key={idx} style={tdStyle}>
          <Input
            name={`rate-${bank.id}-${idx}`}
            value={rateGrid[`rate-${bank.id}-${idx}`] ?? ""}
            onChange={(e) => setRate(bank.id, idx, e.target.value)}
            placeholder="—"
            style={{ width: "6rem" }}
          />
        </td>
      ))}
      <td style={tdStyle}>
        <label className={styles.deleteLabel}>
          <input
            type="checkbox"
            name={`bank-${bank.id}-delete`}
            value="1"
            checked={toDelete}
            onChange={toggleDelete}
          />
          delete
        </label>
      </td>
    </tr>
  );
}
