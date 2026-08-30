import { useQueryClient } from "@tanstack/react-query";

import {
  useDiscounts,
  toggleDiscount,
  type DiscountCodeRow,
} from "../api/featureFlags";
import { ApiError } from "../lib/api";
import { formatDate } from "../lib/datetime";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Loading,
  PageHeader,
  PageShell,
  Pill,
  Table,
  useToast,
} from "../components/ui";

export default function SuperadminDiscounts() {
  const { data, isLoading, isError } = useDiscounts();
  const qc = useQueryClient();
  const toast = useToast();

  async function handleToggle(row: DiscountCodeRow) {
    try {
      await toggleDiscount(row.id, !row.is_active);
      void qc.invalidateQueries({ queryKey: ["superadmin-discounts"] });
      toast({
        message: `${row.code} → ${!row.is_active ? "active" : "disabled"}`,
        tone: "success",
      });
    } catch (err) {
      toast({
        message: err instanceof ApiError ? err.message : "Toggle failed",
        tone: "error",
      });
    }
  }

  return (
    <PageShell gap="1.25rem">
      <PageHeader
        title="Discount Codes"
        subtitle="Stripe coupon codes — toggle visibility, view redemptions"
      />

      {isLoading && <Loading />}
      {isError && <Alert tone="error">Could not load discount codes.</Alert>}

      {data && data.rows.length === 0 && (
        <EmptyState
          title="No discount codes"
          body="Coupon codes created in Stripe will appear here."
        />
      )}

      {data && data.rows.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Value</th>
                <th>Duration</th>
                <th>Redeemed</th>
                <th>Expires</th>
                <th>Status</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.id}>
                  <td style={{ fontFamily: "var(--db-font-mono, monospace)", fontWeight: 600 }}>
                    {row.code}
                  </td>
                  <td>{row.value_label}</td>
                  <td style={{ fontSize: "0.85rem" }}>
                    {row.duration === "repeating" && row.duration_in_months
                      ? `${row.duration_in_months} mo`
                      : row.duration}
                  </td>
                  <td style={{ fontFamily: "var(--db-font-mono, monospace)" }}>
                    {row.redeemed_count}
                    {row.max_redemptions != null && (
                      <span style={{ color: "var(--db-text-muted)" }}>
                        {" "}/ {row.max_redemptions}
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: "0.82rem", color: "var(--db-text-muted)" }}>
                    {formatDate(row.expires_at)}
                  </td>
                  <td>
                    {row.is_redeemable ? (
                      <Pill tone="accent">Redeemable</Pill>
                    ) : row.is_active ? (
                      <Pill tone="warning">Capped / Expired</Pill>
                    ) : (
                      <Pill tone="neutral">Disabled</Pill>
                    )}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <Button
                      size="sm"
                      tone="secondary"
                      onClick={() => { void handleToggle(row); }}
                    >
                      {row.is_active ? "Disable" : "Enable"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div style={{ padding: "0.75rem 1rem", fontSize: "0.82rem", color: "var(--db-text-muted)" }}>
            {data.total} code{data.total !== 1 ? "s" : ""} total.
            Coupon creation is managed in the Stripe Dashboard.
          </div>
        </Card>
      )}
    </PageShell>
  );
}
