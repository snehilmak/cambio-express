import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useCustomerSearch,
  type CustomerRow,
} from "../api/customers";
import { getCurrentIdentity } from "../lib/auth";
import { maskPhone } from "../lib/format";
import {
  Card, Empty, EmptyState, ErrorState, Field, Input, PageHeader, PageShell,
  Section, Table, tdStyle, thStyle,
} from "../components/ui";
import styles from "./Customers.module.css";

// Customer search at /app/customers. Live-search box; results
// split into "exact matches" (phone/full-name match) and
// "suggestions" (fuzzy near-misses) — same shape the legacy
// /api/customers/search returns.
//
// Search query lives in the URL query string so refresh + back
// preserve state, just like the transfers list.
export default function Customers() {
  const identity = getCurrentIdentity();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";

  const [draft, setDraft] = useState(q);
  // 300ms debounce + 2-char minimum (CLAUDE.md "Table search UX").
  useEffect(() => {
    if (draft === q) return;
    const id = window.setTimeout(() => {
      const next = draft.length === 0 || draft.length >= 2 ? draft : q;
      const params = new URLSearchParams(searchParams);
      if (next) params.set("q", next);
      else params.delete("q");
      setSearchParams(params, { replace: true });
    }, 300);
    return () => window.clearTimeout(id);
  }, [draft, q, searchParams, setSearchParams]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror URL search param into local debounced input when URL changes externally (browser back, link arrival)
  useEffect(() => { setDraft(q); }, [q]);

  const { data, isFetching, isError, error, refetch } = useCustomerSearch(q);

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="70rem">
        <PageHeader title="Customers" />
        <Empty>Sign in as a store admin to search this store's customers.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="70rem">
      <PageHeader
        title="Customers"
        subtitle={q.length >= 2
          ? data
            ? `${data.matches.length} match${
                data.matches.length === 1 ? "" : "es"
              } · ${data.suggestions.length} suggestion${
                data.suggestions.length === 1 ? "" : "s"
              }`
            : "Searching…"
          : "Type at least 2 characters to search."}
      />

      <Card style={{ marginBottom: "1rem" }}>
        <Field label="Search">
          <Input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Name, phone, …"
          />
        </Field>
        {isFetching && (
          <p className={styles.searching}>Searching…</p>
        )}
      </Card>

      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Search failed"}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && data.matches.length > 0 && (
        <Section title="Matches">
          <Card>
            <CustomerTable rows={data.matches} />
          </Card>
        </Section>
      )}

      {data && data.suggestions.length > 0 && (
        <Section title="Suggestions">
          <Card>
            <CustomerTable rows={data.suggestions} />
          </Card>
        </Section>
      )}

      {data &&
        data.matches.length === 0 &&
        data.suggestions.length === 0 &&
        q.length >= 2 &&
        !isFetching && (
          <EmptyState title={`No customers match "${q}".`} />
        )}
    </PageShell>
  );
}

function CustomerTable({ rows }: { rows: CustomerRow[] }) {
  return (
    <Table>
      <thead>
        <tr>
          {["Name", "Phone", "DOB", "Address", "Home store"].map((h) => (
            <th key={h} style={thStyle}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.id}>
            <td style={tdStyle}>
              <strong>{c.full_name}</strong>
            </td>
            <td style={tdStyle}>
              <span
                className={styles.phone}
                // Full number copied to clipboard via the row's
                // detail page; the list view only shows the last
                // 4 digits per compliance (over-the-shoulder PII).
                title="Open the customer for the full number"
              >
                {c.phone_country} {maskPhone(c.phone_number)}
              </span>
            </td>
            <td style={tdStyle}>
              <span className={styles.dob}>
                {c.dob || "—"}
              </span>
            </td>
            <td style={tdStyle}>{c.address || "—"}</td>
            <td style={tdStyle}>
              <span className={styles.muted}>
                {c.home_store_name || "(this store)"}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
