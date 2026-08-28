import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity, persistLoginResponse } from "../lib/auth";
import type { components } from "./openapi";

// Owner store-switching (U-2, single-dashboard principle): an
// owner ENTERS a store and sees the exact store view their team
// sees; the Switch Store modal changes which store that one
// dashboard shows. The server sets the store-scoped cookie; we
// persist the returned claims + remember the active store so a
// silent refresh (which re-mints the base owner token) can
// re-enter it (see lib/api._silentRefresh).

export type SwitchableStoreRow = components["schemas"]["SwitchableStoreRow"];
type MyStoresResponse = components["schemas"]["MyStoresResponse"];
export type SwitchStoreResult = components["schemas"]["SwitchStoreResponse"];

export const ACTIVE_STORE_KEY = "db.owner_active_store";
const FAVORITES_KEY = "db.store_favorites";

/** True when this session can use the store switcher: a base
 *  owner login, or an owner already switched into a store. */
export function isOwnerSession(): boolean {
  const identity = getCurrentIdentity();
  return identity != null
    && (identity.role === "owner" || identity.owner_id != null);
}

export function useMyStores(enabled: boolean) {
  return useQuery<MyStoresResponse>({
    enabled,
    queryKey: ["auth", "my-stores"],
    queryFn: () => api<MyStoresResponse>("/api/v2/auth/my-stores"),
  });
}

export async function switchStore(
  storeId: number,
): Promise<SwitchStoreResult> {
  const body = await api<SwitchStoreResult>("/api/v2/auth/switch-store", {
    method: "POST", json: { store_id: storeId },
  });
  persistLoginResponse(body);
  try {
    window.localStorage.setItem(ACTIVE_STORE_KEY, String(body.store_id));
  } catch { /* per-device convenience only */ }
  return body;
}

/** Leave the store context: forget the remembered store and let a
 *  refresh re-mint the base owner token (server persists no switch
 *  state — see Auth INVARIANTS.md). */
export async function returnToOwnerView(): Promise<void> {
  try {
    window.localStorage.removeItem(ACTIVE_STORE_KEY);
  } catch { /* ignore */ }
  const resp = await fetch("/api/v2/auth/refresh", {
    method: "POST", credentials: "include",
  });
  if (resp.ok) {
    const body: unknown = await resp.json();
    if (typeof body === "object" && body
        && typeof (body as { user_id?: unknown }).user_id === "number") {
      persistLoginResponse(body as Parameters<typeof persistLoginResponse>[0]);
    }
  }
}

/** Owner just logged in (U-4a, single-dashboard rule): drop them
 *  straight into a store so their landing view is the same one
 *  their team sees. Preference: the store remembered on this
 *  device → the owner's home store → the first switchable store.
 *  Returns false when the owner has no active stores (legacy
 *  connect-code owners) — the caller falls back to the owner
 *  overview. */
export async function autoEnterOwnerStore(): Promise<boolean> {
  let rows: SwitchableStoreRow[];
  try {
    const body = await api<MyStoresResponse>("/api/v2/auth/my-stores");
    rows = body.stores;
  } catch {
    return false;
  }
  if (rows.length === 0) return false;
  const remembered = rememberedStoreId();
  const target =
    rows.find((s) => s.store_id === remembered)
    ?? rows.find((s) => s.is_home)
    ?? rows[0];
  try {
    await switchStore(target.store_id);
    return true;
  } catch {
    return false;
  }
}

export function rememberedStoreId(): number | null {
  try {
    const raw = window.localStorage.getItem(ACTIVE_STORE_KEY);
    const id = raw != null ? Number(raw) : NaN;
    return Number.isFinite(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

// ── Favorite stores (per-device convenience) ─────────────────

export function favoriteStoreIds(): Set<number> {
  try {
    const raw = window.localStorage.getItem(FAVORITES_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(
      Array.isArray(parsed)
        ? parsed.filter((v): v is number => typeof v === "number")
        : [],
    );
  } catch {
    return new Set();
  }
}

export function toggleFavoriteStore(storeId: number): Set<number> {
  const favs = favoriteStoreIds();
  if (favs.has(storeId)) favs.delete(storeId);
  else favs.add(storeId);
  try {
    window.localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favs]));
  } catch { /* ignore */ }
  return favs;
}
