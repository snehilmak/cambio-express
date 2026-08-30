import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { useUrlFilterState } from "../lib/useUrlFilterState";
import {
  Breadcrumbs, Card, EmptyState, ErrorState, Input, Loading, PageHeader, PageShell,
  Pager, Pill, Table,
} from "../components/ui";

interface UserRow {
  id: number;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
  store_id: number;
  store_name: string;
}

interface UsersResponse {
  rows: UserRow[];
  total: number;
  page: number;
  total_pages: number;
}

function useOwnerUsers(storeId: number | null, q: string, page: number) {
  const identity = getCurrentIdentity();
  const params = new URLSearchParams();
  if (storeId) params.set("store_id", String(storeId));
  if (q) params.set("q", q);
  params.set("page", String(page));
  return useQuery<UsersResponse>({
    enabled: identity?.role === "owner",
    queryKey: ["owner-users", storeId, q, page],
    queryFn: () => api<UsersResponse>(`/api/v2/owner/users?${params}`),
  });
}

export default function OwnerUsers() {
  const filters = useUrlFilterState({ q: "" });
  const { data, isLoading, isError, refetch } = useOwnerUsers(null, filters.params.q, filters.page);
  const setPage = filters.setPage;

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[
        { label: "Locations", to: "/owner/locations" },
        { label: "Team users" },
      ]} />
      <PageHeader
        title="Team Users"
        subtitle="Users across all your linked stores"
      />

      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
        <Input
          style={{ width: "16rem" }}
          placeholder="Search by name or username…"
          value={filters.draft.q ?? filters.params.q}
          onChange={(e) => filters.debounced("q", e.target.value)}
        />
      </div>

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message="Could not load users."
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && data.rows.length === 0 && (
        <EmptyState title="No users found" body="No matching users across your stores." />
      )}

      {data && data.rows.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Username</th>
                <th>Role</th>
                <th>Store</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((u) => (
                <tr key={u.id}>
                  <td style={{ fontWeight: 500 }}>{u.full_name || "—"}</td>
                  <td style={{ fontFamily: "var(--db-font-mono, monospace)", fontSize: "0.85rem" }}>
                    {u.username}
                  </td>
                  <td>
                    <Pill tone={u.role === "admin" ? "accent" : "neutral"}>
                      {u.role}
                    </Pill>
                  </td>
                  <td>{u.store_name}</td>
                  <td>
                    <Pill tone={u.is_active ? "accent" : "neutral"}>
                      {u.is_active ? "Active" : "Inactive"}
                    </Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          {data.total_pages > 1 && (
            <Pager
              page={data.page}
              totalPages={data.total_pages}
              onPage={setPage}
              leading={
                <span style={{ fontSize: "0.85rem", color: "var(--db-text-muted)" }}>
                  {data.total} users
                </span>
              }
            />
          )}
        </Card>
      )}
    </PageShell>
  );
}
