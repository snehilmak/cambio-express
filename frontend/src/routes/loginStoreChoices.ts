// Shared by the sign-in page (L-1). Kept as a pure module so the
// parsing rules are unit-testable without mounting the login form.
import { ApiError } from "../lib/api";

/** One option in the "which store?" step — returned by
 *  /login-cross-store when the credentials authenticate at more
 *  than one store. */
export interface StoreChoice {
  store_id: number;
  store_name: string;
  role: string;
}

/** Pull the store list out of a 409 `store_ambiguous` response.
 *
 *  Returns null for every other failure so ordinary errors (bad
 *  password, network, the TOTP-enrollment 409) still render as
 *  errors rather than an empty picker.
 */
export function readStoreChoices(err: unknown): StoreChoice[] | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const body = err.body as
    { detail?: { code?: string; stores?: StoreChoice[] } } | undefined;
  const detail = body?.detail;
  if (detail?.code !== "store_ambiguous") return null;
  const stores = detail.stores;
  return Array.isArray(stores) && stores.length > 0 ? stores : null;
}
