import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { formatTimestamp } from "../lib/datetime";
import {
  Breadcrumbs, Card, EmptyState, Input, Loading, PageHeader, PageShell,
  Pill, Table,
} from "../components/ui";

interface ActivityRow {
  type: string;
  store_id: number;
  store_name: string;
  user_name: string;
  user_role: string;
  action: string;
  target_type: string;
  target_label: string;
  summary: string;
  created_at: string;
}

interface ActivityResponse {
  rows: ActivityRow[];
  total: number;
  page: number;
  total_pages: number;
}

function useOwnerActivity(q: string, page: number) {
  const identity = getCurrentIdentity();
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  params.set("page", String(page));
  return useQuery<ActivityResponse>({
    enabled: identity?.role === "owner",
    queryKey: ["owner-activity", q, page],
    queryFn: () => api<ActivityResponse>(`/api/v2/owner/activity?${params}`),
  });
}

export default function OwnerActivity() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading, isError } = useOwnerActivity(debouncedSearch, page);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleSearch(val: string) {
    setSearch(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(val);
      setPage(1);
    }, 300);
  }

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[{ label: "Activity stream" }]} />
      <PageHeader
        title="Activity Stream"
        subtitle="Recent actions across all your stores"
      />

      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
        <Input
          style={{ width: "20rem" }}
          placeholder="Search by user, action, or summary…"
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
        />
      </div>

      {isLoading && <Loading />}
      {isError && <EmptyState title="Error" body="Could not load activity." />}

      {data && data.rows.length === 0 && (
        <EmptyState title="No activity" body="No matching events found." />
      )}

      {data && data.rows.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Store</th>
                <th>User</th>
                <th>Action</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={i}>
                  <td style={{ whiteSpace: "nowrap", fontFamily: "var(--db-font-mono, monospace)", fontSize: "0.8rem" }}>
                    {r.created_at ? formatTimestamp(r.created_at) : "—"}
                  </td>
                  <td>
                    <Pill tone="neutral">{r.store_name || `#${r.store_id}`}</Pill>
                  </td>
                  <td style={{ fontWeight: 500 }}>
                    {r.user_name || "—"}
                    {r.user_role && (
                      <span style={{ color: "var(--db-text-muted)", fontSize: "0.8rem", marginLeft: "0.25rem" }}>
                        ({r.user_role})
                      </span>
                    )}
                  </td>
                  <td>
                    <Pill tone={r.type === "transfer" ? "accent" : "neutral"}>
                      {r.action}
                    </Pill>
                  </td>
                  <td style={{ maxWidth: "20rem", overflow: "hidden", textOverflow: "ellipsis", fontSize: "0.85rem" }}>
                    {r.summary || r.target_label || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          {data.total_pages > 1 && (
            <div style={{ display: "flex", justifyContent: "center", gap: "0.5rem", padding: "0.75rem" }}>
              <button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
              <span style={{ fontSize: "0.85rem", color: "var(--db-text-muted)" }}>
                Page {data.page} of {data.total_pages} ({data.total} events)
              </span>
              <button type="button" aria-label="Next page" disabled={page >= data.total_pages} onClick={() => setPage(page + 1)}>Next →</button>
            </div>
          )}
        </Card>
      )}
    </PageShell>
  );
}
