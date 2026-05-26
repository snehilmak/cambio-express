import type { ReactNode } from "react";

import { EmptyState } from "./Empty";
import { ErrorState } from "./ErrorState";
import { TableSkeleton } from "./Table";

/**
 * Three-state guard for paginated table views: loading skeleton,
 * error with retry, or empty state. Renders nothing when data is
 * present and non-empty — the caller renders the table itself.
 *
 * Usage:
 * ```tsx
 * <Card>
 *   <TableStates
 *     isLoading={isLoading}
 *     isError={isError}
 *     error={error}
 *     isEmpty={data?.rows.length === 0}
 *     onRetry={() => refetch()}
 *     errorMessage="Could not load transfers"
 *     emptyTitle="No transfers match these filters."
 *   />
 *   {data && data.rows.length > 0 && <MyTable rows={data.rows} />}
 * </Card>
 * ```
 */
export function TableStates({
  isLoading,
  isError,
  error,
  isEmpty,
  onRetry,
  errorMessage,
  emptyTitle,
  emptyBody,
  rows = 5,
  cols = 5,
}: {
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  isEmpty: boolean;
  onRetry: () => void;
  errorMessage?: string;
  emptyTitle: string;
  emptyBody?: ReactNode;
  rows?: number;
  cols?: number;
}) {
  if (isLoading) {
    return <TableSkeleton rows={rows} cols={cols} />;
  }
  if (isError) {
    return (
      <ErrorState
        message={
          errorMessage ??
          (error instanceof Error ? error.message : "Could not load data")
        }
        onRetry={onRetry}
      />
    );
  }
  if (isEmpty && !isLoading) {
    return <EmptyState title={emptyTitle} body={emptyBody} />;
  }
  return null;
}
