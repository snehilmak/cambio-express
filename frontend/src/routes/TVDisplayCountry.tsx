import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useTVDisplayCountryDetail,
  type TVDisplayBankRow,
} from "../api/tvDisplay";

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
  const { data, isLoading, isError, error } =
    useTVDisplayCountryDetail(cid);

  const [companiesText, setCompaniesText] = useState("");
  const [bankNames, setBankNames] = useState<Record<number, string>>({});
  const [bankSorts, setBankSorts] = useState<Record<number, number>>({});
  const [bankDeletes, setBankDeletes] = useState<Set<number>>(new Set());
  const [newBankNames, setNewBankNames] = useState<string[]>([""]);
  const [rateGrid, setRateGrid] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data) return;
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
      <main style={pageStyle}>
        <p style={muted}>Loading country…</p>
      </main>
    );
  }
  if (isError || !data) {
    return (
      <main style={pageStyle}>
        <p style={errorStyle}>
          Couldn't load country —{" "}
          {error instanceof Error ? error.message : "unknown error"}
        </p>
      </main>
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
    <main style={pageStyle}>
      <header>
        <Link to="/tv-display" style={backLink}>← Back to TV Display</Link>
        <h1 style={titleStyle}>{data.country_name || "Country"}</h1>
        <p style={muted}>
          {data.country_code} · {data.banks.length} bank
          {data.banks.length === 1 ? "" : "s"} · {data.mt_companies.length} company column
          {data.mt_companies.length === 1 ? "" : "s"}
        </p>
      </header>

      <form
        method="POST"
        action={`/tv-display/countries/${cid}`}
        style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}
      >
        <section style={cardStyle}>
          <h2 style={cardH2}>Country header</h2>
          <Field label="Country name">
            <input
              name="country_name"
              defaultValue={data.country_name}
              maxLength={80}
              style={inputStyle}
            />
          </Field>
          <Field label="ISO country code">
            <input
              name="country_code"
              defaultValue={data.country_code}
              maxLength={4}
              style={inputStyle}
            />
          </Field>
          <Field label="MT companies (comma-separated slugs)">
            <input
              name="mt_companies"
              value={companiesText}
              onChange={(e) => setCompaniesText(e.target.value)}
              maxLength={500}
              style={inputStyle}
            />
            <small style={muted}>
              These become the column headers in the public board's rate grid.
              Order is preserved.
            </small>
          </Field>
        </section>

        <section style={cardStyle}>
          <h2 style={cardH2}>Banks &amp; rate matrix</h2>
          <table style={tableStyle}>
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
          </table>
        </section>

        <section style={cardStyle}>
          <h2 style={cardH2}>Add new banks</h2>
          {newBankNames.map((name, idx) => (
            <input
              key={idx}
              name="new_bank_name"
              value={name}
              onChange={(e) => setNewBankAt(idx, e.target.value)}
              placeholder="Bank name (leave blank to skip)"
              maxLength={120}
              style={{ ...inputStyle, marginBottom: "0.5rem" }}
            />
          ))}
        </section>

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button type="submit" style={btnPrimary}>Save changes</button>
          <Link to="/tv-display" style={btnOutlineLink}>Cancel</Link>
        </div>
      </form>
    </main>
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
    <tr style={toDelete ? { opacity: 0.4 } : undefined}>
      <td style={tdStyle}>
        <input
          name={`bank-${bank.id}-name`}
          value={bankName}
          onChange={(e) => setBankName(e.target.value)}
          maxLength={120}
          style={inputSmall}
        />
      </td>
      <td style={tdStyle}>
        <input
          name={`bank-${bank.id}-sort`}
          type="number"
          value={bankSort}
          onChange={(e) => setBankSort(Number(e.target.value) || 0)}
          style={{ ...inputSmall, width: "5rem" }}
        />
      </td>
      {companies.map((_, idx) => (
        <td key={idx} style={tdStyle}>
          <input
            name={`rate-${bank.id}-${idx}`}
            value={rateGrid[`rate-${bank.id}-${idx}`] ?? ""}
            onChange={(e) => setRate(bank.id, idx, e.target.value)}
            placeholder="—"
            style={{ ...inputSmall, width: "6rem" }}
          />
        </td>
      ))}
      <td style={tdStyle}>
        <label style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block", marginBottom: "0.75rem" }}>
      <div style={fieldLabel}>{label}</div>
      {children}
    </label>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1, padding: "2rem 1.5rem", maxWidth: "75rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
  display: "flex", flexDirection: "column", gap: "1.25rem",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)", fontWeight: 600,
  margin: "0.25rem 0 0",
};
const backLink: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)",
  textDecoration: "none", fontSize: "0.85rem",
};
const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem", padding: "1.25rem",
};
const cardH2: React.CSSProperties = {
  margin: "0 0 0.75rem", fontSize: "1rem",
};
const fieldLabel: React.CSSProperties = {
  fontSize: "0.75rem", textTransform: "uppercase",
  letterSpacing: "0.05em", color: "var(--db-text-muted, #a3a3a3)",
  fontWeight: 600, marginBottom: "0.25rem",
};
const inputStyle: React.CSSProperties = {
  width: "100%", padding: "0.5rem 0.65rem",
  background: "var(--db-surface-1, #0a0a0a)",
  color: "inherit",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.4rem", fontSize: "0.9rem",
  fontFamily: "inherit",
};
const inputSmall: React.CSSProperties = {
  ...inputStyle, padding: "0.3rem 0.5rem", fontSize: "0.85rem",
};
const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse",
};
const thStyle: React.CSSProperties = {
  textAlign: "left", padding: "0.4rem 0.5rem",
  borderBottom: "1px solid var(--db-border, #262626)",
  fontSize: "0.7rem", textTransform: "uppercase",
  color: "var(--db-text-muted, #a3a3a3)", fontWeight: 500,
};
const tdStyle: React.CSSProperties = {
  padding: "0.4rem 0.5rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};
const btnPrimary: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)", color: "#000",
  border: "none", padding: "0.6rem 1.1rem",
  borderRadius: "0.5rem", fontWeight: 600,
  fontSize: "0.9rem", cursor: "pointer",
};
const btnOutlineLink: React.CSSProperties = {
  background: "transparent", color: "inherit",
  border: "1px solid var(--db-border, #262626)",
  padding: "0.6rem 1.1rem", borderRadius: "0.5rem",
  fontSize: "0.9rem", cursor: "pointer",
  textDecoration: "none", display: "inline-block",
};
const muted: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem", margin: 0,
};
const errorStyle: React.CSSProperties = {
  color: "var(--db-negative, #ff3b30)",
  background: "rgba(255,59,48,0.08)",
  border: "1px solid rgba(255,59,48,0.4)",
  padding: "0.75rem 1rem", borderRadius: "0.5rem",
};
